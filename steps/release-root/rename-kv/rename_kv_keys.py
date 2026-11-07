#!/usr/bin/env python3
"""Rename the key-value metadata keys in a Parquet footer.

Only the footer changes.  The output file is the input bytes up to the start
of the footer (the "data prefix"), then a new Thrift FileMetaData, then the
4-byte footer length and "PAR1".  Column chunk, page index and bloom filter
offsets are absolute from the file start, so the data prefix stays the same.

The Thrift compact protocol reader and writer in this file are generic: the
reader keeps every field, its type, and how its header was encoded (short
delta form or long form), so the writer gives the same bytes back.  Before
it changes a footer, the tool encodes the parsed footer again and stops if
the bytes are not identical to the original footer.

Rename rule: a key that starts with "organisations_" starts with
"organizations_" in the output.  No other byte of the footer changes.  The
tool stops if a string other than these keys changes, or if the kv metadata
or the schema names still contain "organis" (case insensitive).  Column
statistics hold data values (for example file paths of a project); they are
third-party text and the tool does not change them.

Sub-commands:
  scan  SRC_DIR OUT_TSV           read all footers; list kv keys and every
                                  footer string with "organis"
  one   SRC DST                   rename one file (no DuckDB check)
  run   SRC_DIR DST_DIR LOG_TSV   rename and check all files, in parallel,
        [--jobs N] [--sums FILE]  resume-safe; --sums is the release
        [--only NAME ...]         SHA256SUMS to check the inputs against
  content SRC DST                 full content check with DuckDB
                                  (count(*), sum(hash(*)) of all columns)

Runtime: Python 3.12 with duckdb 1.5.5 (the ctp venv), run with -I.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

OLD_PREFIX = b"organisations_"
NEW_PREFIX = b"organizations_"
PROBE = b"organis"
MAGIC = b"PAR1"
FICLONE = 0x40049409
CHUNK = 8 << 20

# ---------------------------------------------------------------- Thrift --
# Compact protocol type ids.
T_STOP, T_TRUE, T_FALSE, T_I8, T_I16, T_I32, T_I64, T_DOUBLE = 0, 1, 2, 3, 4, 5, 6, 7
T_BINARY, T_LIST, T_SET, T_MAP, T_STRUCT, T_UUID = 8, 9, 10, 11, 12, 13


class Field:
    """One struct field.  `short` is True when the header used the delta form."""

    __slots__ = ("fid", "ttype", "value", "short")

    def __init__(self, fid, ttype, value, short):
        self.fid, self.ttype, self.value, self.short = fid, ttype, value, short


class TList:
    __slots__ = ("etype", "items", "short", "ttype")

    def __init__(self, ttype, etype, items, short):
        self.ttype, self.etype, self.items, self.short = ttype, etype, items, short


class TMap:
    __slots__ = ("ktype", "vtype", "items")

    def __init__(self, ktype, vtype, items):
        self.ktype, self.vtype, self.items = ktype, vtype, items


class Reader:
    def __init__(self, buf: bytes):
        self.b = buf
        self.p = 0

    def byte(self) -> int:
        v = self.b[self.p]
        self.p += 1
        return v

    def varint(self) -> int:
        shift = res = 0
        while True:
            c = self.byte()
            res |= (c & 0x7F) << shift
            if not c & 0x80:
                return res
            shift += 7

    def zigzag(self) -> int:
        n = self.varint()
        return (n >> 1) ^ -(n & 1)

    def value(self, t: int, in_container: bool = False):
        if t in (T_TRUE, T_FALSE):
            # In a struct field the value is in the type nibble; in a
            # container it is one byte.  Keep the raw byte.
            return self.byte() if in_container else None
        if t == T_I8:
            return self.byte()
        if t in (T_I16, T_I32, T_I64):
            return self.zigzag()
        if t == T_DOUBLE:
            v = self.b[self.p:self.p + 8]
            self.p += 8
            return v
        if t == T_UUID:
            v = self.b[self.p:self.p + 16]
            self.p += 16
            return v
        if t == T_BINARY:
            n = self.varint()
            v = self.b[self.p:self.p + n]
            if len(v) != n:
                raise ValueError("binary runs past the footer")
            self.p += n
            return v
        if t in (T_LIST, T_SET):
            h = self.byte()
            etype = h & 0x0F
            size = h >> 4
            short = size != 15
            if not short:
                size = self.varint()
            return TList(t, etype, [self.value(etype, True) for _ in range(size)], short)
        if t == T_MAP:
            size = self.varint()
            if size == 0:
                return TMap(None, None, [])
            kv = self.byte()
            kt, vt = kv >> 4, kv & 0x0F
            return TMap(kt, vt, [(self.value(kt, True), self.value(vt, True)) for _ in range(size)])
        if t == T_STRUCT:
            return self.struct()
        raise ValueError(f"unknown compact type {t} at {self.p}")

    def struct(self) -> list:
        fields = []
        last = 0
        while True:
            h = self.byte()
            if h == T_STOP:
                return fields
            t = h & 0x0F
            delta = h >> 4
            if delta:
                fid, short = last + delta, True
            else:
                fid, short = self.zigzag(), False
            if t in (T_TRUE, T_FALSE):
                val = None
            else:
                val = self.value(t)
            fields.append(Field(fid, t, val, short))
            last = fid


class Writer:
    def __init__(self):
        self.out = bytearray()

    def varint(self, n: int):
        while True:
            if n < 0x80:
                self.out.append(n)
                return
            self.out.append((n & 0x7F) | 0x80)
            n >>= 7

    def zigzag(self, v: int, bits: int):
        self.varint(((v << 1) ^ (v >> (bits - 1))) & ((1 << bits) - 1))

    def value(self, t: int, v, in_container: bool = False):
        if t in (T_TRUE, T_FALSE):
            if in_container:
                self.out.append(v)
            return
        if t == T_I8:
            self.out.append(v)
        elif t == T_I16:
            self.zigzag(v, 16)
        elif t == T_I32:
            self.zigzag(v, 32)
        elif t == T_I64:
            self.zigzag(v, 64)
        elif t in (T_DOUBLE, T_UUID):
            self.out += v
        elif t == T_BINARY:
            self.varint(len(v))
            self.out += v
        elif t in (T_LIST, T_SET):
            n = len(v.items)
            if v.short:
                if n >= 15:
                    raise ValueError("short list header with 15 or more items")
                self.out.append((n << 4) | v.etype)
            else:
                self.out.append(0xF0 | v.etype)
                self.varint(n)
            for it in v.items:
                self.value(v.etype, it, True)
        elif t == T_MAP:
            self.varint(len(v.items))
            if v.items:
                self.out.append((v.ktype << 4) | v.vtype)
                for k, x in v.items:
                    self.value(v.ktype, k, True)
                    self.value(v.vtype, x, True)
        elif t == T_STRUCT:
            self.struct(v)
        else:
            raise ValueError(f"unknown compact type {t}")

    def struct(self, fields: list):
        last = 0
        for f in fields:
            delta = f.fid - last
            if f.short:
                if not 0 < delta <= 15:
                    raise ValueError("short field header with a bad delta")
                self.out.append((delta << 4) | f.ttype)
            else:
                self.out.append(f.ttype)
                self.zigzag(f.fid, 16)
            if f.ttype not in (T_TRUE, T_FALSE):
                self.value(f.ttype, f.value)
            last = f.fid
        self.out.append(T_STOP)


def parse_footer(footer: bytes) -> list:
    r = Reader(footer)
    meta = r.struct()
    if r.p != len(footer):
        raise ValueError(f"footer has {len(footer) - r.p} bytes after FileMetaData")
    return meta


def encode(meta: list) -> bytes:
    w = Writer()
    w.struct(meta)
    return bytes(w.out)


def walk_strings(obj, path=""):
    """Yield (path, bytes) for every BINARY value in the tree."""
    if isinstance(obj, list):  # struct
        for f in obj:
            yield from walk_value(f.ttype, f.value, f"{path}.{f.fid}")


def walk_value(t, v, path):
    if t == T_BINARY:
        yield path, v
    elif t == T_STRUCT:
        yield from walk_strings(v, path)
    elif t in (T_LIST, T_SET):
        for i, it in enumerate(v.items):
            yield from walk_value(v.etype, it, f"{path}[{i}]")
    elif t == T_MAP:
        for i, (k, x) in enumerate(v.items):
            yield from walk_value(v.ktype, k, f"{path}{{{i}}}k")
            yield from walk_value(v.vtype, x, f"{path}{{{i}}}v")


def kv_list(meta: list):
    """FileMetaData field 5 = key_value_metadata: list<KeyValue{1:key,2:value}>."""
    for f in meta:
        if f.fid == 5:
            if f.ttype != T_LIST or f.value.etype != T_STRUCT:
                raise ValueError("field 5 is not list<struct>")
            out = []
            for kv in f.value.items:
                d = {g.fid: g for g in kv}
                if 1 not in d or d[1].ttype != T_BINARY:
                    raise ValueError("KeyValue without a binary key")
                out.append((kv, d[1], d.get(2)))
            return out
    return []


def kv_pairs(meta: list):
    return [(k.value.decode(), None if v is None else v.value.decode()) for _, k, v in kv_list(meta)]


# ------------------------------------------------------------- file level --
def read_footer(path: str):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(4)
        fh.seek(size - 8)
        tail = fh.read(8)
        flen = struct.unpack("<I", tail[:4])[0]
        if head != MAGIC or tail[4:] != MAGIC:
            raise ValueError(f"{path}: no PAR1 magic")
        start = size - 8 - flen
        if start < 4:
            raise ValueError(f"{path}: bad footer length {flen}")
        fh.seek(start)
        footer = fh.read(flen)
    return size, start, flen, footer


def renamed_footer(footer: bytes):
    """Return (new_footer, kv_before, kv_after).  Stops on any doubt."""
    meta = parse_footer(footer)
    if encode(meta) != footer:
        raise ValueError("Thrift round trip is not byte-identical")
    before = kv_pairs(meta)
    strings_before = list(walk_strings(meta))
    key_paths = set()
    for i, (_, kf, _) in enumerate(kv_list(meta)):
        if kf.value.startswith(OLD_PREFIX):
            kf.value = NEW_PREFIX + kf.value[len(OLD_PREFIX):]
            key_paths.add(f".5[{i}].1")
    after = kv_pairs(meta)
    strings_after = list(walk_strings(meta))
    # Only the renamed kv keys may differ; every other string stays the same.
    if [p for p, _ in strings_before] != [p for p, _ in strings_after]:
        raise ValueError("string paths differ after the rename")
    diff = {p for (p, a), (_, b) in zip(strings_before, strings_after) if a != b}
    if diff != key_paths:
        raise ValueError(f"unexpected changed strings: {sorted(diff ^ key_paths)}")
    # Our vocabulary is in the kv metadata (field 5) and the schema names
    # (field 2).  Statistics (field 4) hold data values, for example file
    # paths of a project; they are third-party text and do not change.
    hits = [p for p, s in strings_after if PROBE in s.lower() and (p.startswith(".5[") or p.startswith(".2["))]
    if hits:
        raise ValueError(f"kv metadata or schema still has 'organis' after the rename: {hits}")
    new = encode(meta)
    # Independent check: parse the new bytes again.
    meta2 = parse_footer(new)
    if encode(meta2) != new or kv_pairs(meta2) != after:
        raise ValueError("new footer does not parse back to the same tree")
    return new, before, after


def clone_or_copy(src: str, dst_fd: int, src_fd: int, length: int) -> str:
    try:
        fcntl.ioctl(dst_fd, FICLONE, src_fd)
        os.ftruncate(dst_fd, length)
        return "reflink"
    except OSError:
        os.ftruncate(dst_fd, 0)
        off = 0
        if hasattr(os, "copy_file_range"):
            while off < length:
                n = os.copy_file_range(src_fd, dst_fd, min(CHUNK * 8, length - off), off, off)
                if n <= 0:
                    raise OSError("copy_file_range returned 0")
                off += n
            return "copy"
        # A Python with no os.copy_file_range: a plain read and write of the same bytes.
        while off < length:
            buf = os.pread(src_fd, min(CHUNK * 8, length - off), off)
            if not buf:
                raise OSError("short read of the data prefix")
            os.pwrite(dst_fd, buf, off)
            off += len(buf)
        return "read-write"


def write_renamed(src: str, dst: str):
    size, start, flen, footer = read_footer(src)
    new, before, after = renamed_footer(footer)
    tmp = dst + ".tmp"
    sfd = os.open(src, os.O_RDONLY)
    dfd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        mode = clone_or_copy(src, dfd, sfd, start)
        os.lseek(dfd, start, os.SEEK_SET)
        tail = new + struct.pack("<I", len(new)) + MAGIC
        os.write(dfd, tail)
        os.fsync(dfd)
    finally:
        os.close(sfd)
        os.close(dfd)
    st = os.stat(src)
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(tmp, dst)
    return dict(in_size=size, prefix_len=start, in_footer_len=flen, out_footer_len=len(new),
                kv_before=before, kv_after=after, copy_mode=mode)


def hash_file(path: str, prefix_len: int):
    """Return (sha256 of the whole file, sha256 of bytes [0, prefix_len))."""
    h = hashlib.sha256()
    hp = None
    done = 0
    with open(path, "rb", buffering=0) as fh:
        while True:
            want = CHUNK
            if hp is None and done + want > prefix_len:
                want = prefix_len - done
            b = fh.read(want) if want else b""
            if hp is None and done == prefix_len:
                hp = h.copy()
                b = fh.read(CHUNK)
            if not b:
                break
            h.update(b)
            done += len(b)
    if hp is None:
        hp = h.copy()
    return h.hexdigest(), hp.hexdigest()


# ---------------------------------------------------------------- DuckDB --
_CON = None


def con():
    global _CON
    if _CON is None:
        import duckdb
        _CON = duckdb.connect()
        _CON.execute("SET threads=2")
    return _CON


def q(sql, path):
    return con().execute(sql, [path]).fetchall()


def duck_check(src: str, dst: str):
    c = {}
    s_schema = q("SELECT * EXCLUDE (file_name) FROM parquet_schema(?)", src)
    d_schema = q("SELECT * EXCLUDE (file_name) FROM parquet_schema(?)", dst)
    c["schema_equal"] = s_schema == d_schema
    s_md = q("SELECT * EXCLUDE (file_name) FROM parquet_metadata(?) ORDER BY row_group_id, column_id", src)
    d_md = q("SELECT * EXCLUDE (file_name) FROM parquet_metadata(?) ORDER BY row_group_id, column_id", dst)
    c["metadata_equal"] = s_md == d_md
    c["metadata_sha256"] = hashlib.sha256(repr(d_md).encode()).hexdigest()
    c["row_groups"] = len({r[0] for r in d_md})
    c["column_chunks"] = len(d_md)
    s_fm = q("SELECT * EXCLUDE (file_name) FROM parquet_file_metadata(?)", src)
    d_fm = q("SELECT * EXCLUDE (file_name) FROM parquet_file_metadata(?)", dst)
    c["file_metadata_equal"] = s_fm == d_fm
    s_rows = q("SELECT count(*) FROM read_parquet(?)", src)[0][0]
    d_rows = q("SELECT count(*) FROM read_parquet(?)", dst)[0][0]
    c["num_rows"] = d_rows
    c["rows_equal"] = s_rows == d_rows
    s_kv = q("SELECT key::VARCHAR, value::VARCHAR FROM parquet_kv_metadata(?)", src)
    d_kv = q("SELECT key::VARCHAR, value::VARCHAR FROM parquet_kv_metadata(?)", dst)
    want = [(k.replace("organisations_", "organizations_", 1) if k.startswith("organisations_") else k, v)
            for k, v in s_kv]
    changed = sum(1 for a, b in zip(s_kv, d_kv) if a[0] != b[0])
    c["kv_ok"] = (d_kv == want and len(s_kv) == len(d_kv)
                  and [v for _, v in s_kv] == [v for _, v in d_kv]
                  and not any("organis" in k.lower() for k, _ in d_kv))
    c["kv_keys_changed"] = changed
    return c


def content_check(src: str, dst: str):
    out = {}
    for tag, p in (("in", src), ("out", dst)):
        cols = [r[0] for r in con().execute(
            "SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(?))", [p]).fetchall()]
        expr = ", ".join(f"sum(hash(\"{c}\"))::HUGEINT" for c in cols)
        row = con().execute(f"SELECT count(*), sum(hash(t))::HUGEINT, {expr} FROM read_parquet(?) AS t", [p]).fetchone()
        out[tag] = row
        out[tag + "_cols"] = len(cols)
    out["equal"] = out["in"] == out["out"]
    return out


# ------------------------------------------------------------------ run ---
LOG_COLS = ["file", "status", "copy_mode", "in_size", "out_size", "prefix_len", "in_footer_len",
            "out_footer_len", "in_sha256", "release_sha256_match", "out_sha256", "in_prefix_sha256",
            "out_prefix_sha256", "prefix_equal", "num_rows", "rows_equal", "row_groups",
            "column_chunks", "schema_equal", "metadata_equal", "file_metadata_equal", "kv_ok",
            "kv_keys_changed", "metadata_sha256", "kv_before", "kv_after", "seconds", "error"]


def process(src: str, dst: str, release_sha: str | None):
    t0 = time.time()
    row = {k: "" for k in LOG_COLS}
    row["file"] = os.path.basename(src)
    try:
        info = write_renamed(src, dst)
        row.update({k: info[k] for k in ("copy_mode", "in_size", "prefix_len", "in_footer_len", "out_footer_len")})
        row["kv_before"] = json.dumps(info["kv_before"], separators=(",", ":"))
        row["kv_after"] = json.dumps(info["kv_after"], separators=(",", ":"))
        in_sha, in_pre = hash_file(src, info["prefix_len"])
        out_sha, out_pre = hash_file(dst, info["prefix_len"])
        row.update(in_sha256=in_sha, out_sha256=out_sha, in_prefix_sha256=in_pre, out_prefix_sha256=out_pre,
                   out_size=os.path.getsize(dst), prefix_equal=in_pre == out_pre)
        row["release_sha256_match"] = "" if release_sha is None else (in_sha == release_sha)
        row.update(duck_check(src, dst))
        names_changed = sum(1 for a, b in zip(info["kv_before"], info["kv_after"]) if a[0] != b[0])
        ok = (row["prefix_equal"] and row["schema_equal"] and row["metadata_equal"]
              and row["file_metadata_equal"] and row["rows_equal"] and row["kv_ok"]
              and row["kv_keys_changed"] == 2 and names_changed == 2
              and row["release_sha256_match"] is not False
              and [v for _, v in info["kv_before"]] == [v for _, v in info["kv_after"]])
        row["status"] = "OK" if ok else "FAIL"
    except Exception as e:  # noqa: BLE001 - log every failure, go on
        row["status"] = "ERROR"
        row["error"] = f"{type(e).__name__}: {e}"
    row["seconds"] = round(time.time() - t0, 2)
    return row


def load_sums(path):
    sums = {}
    if path:
        with open(path) as fh:
            for line in fh:
                h, name = line.rstrip("\n").split("  ", 1)
                if name.startswith("parquet/"):
                    sums[name[len("parquet/"):]] = h
    return sums


def load_done(log):
    done = {}
    if os.path.exists(log):
        with open(log) as fh:
            hdr = fh.readline().rstrip("\n").split("\t")
            for line in fh:
                r = dict(zip(hdr, line.rstrip("\n").split("\t")))
                if r.get("status") == "OK":
                    done[r["file"]] = r
    return done


def verify_existing(dst: str, row: dict) -> bool:
    """Resume rule: skip only if the output still has the logged sha256."""
    if not os.path.exists(dst) or os.path.getsize(dst) != int(row["out_size"]):
        return False
    sha, pre = hash_file(dst, int(row["prefix_len"]))
    return sha == row["out_sha256"] and pre == row["in_prefix_sha256"]


def cmd_run(a):
    names = sorted(n for n in os.listdir(a.src_dir) if n.endswith(".parquet"))
    if a.only:
        names = [n for n in names if n in set(a.only)]
    sums = load_sums(a.sums)
    done = load_done(a.log)
    os.makedirs(a.dst_dir, exist_ok=True)
    todo = []
    skipped = 0
    for n in names:
        if n in done and (a.trust_log or verify_existing(os.path.join(a.dst_dir, n), done[n])):
            skipped += 1
            continue
        todo.append(n)
    todo.sort(key=lambda n: -os.path.getsize(os.path.join(a.src_dir, n)))
    print(f"files {len(names)}, skip {skipped} (output passes the check), to do {len(todo)}", flush=True)
    new_log = not os.path.exists(a.log)
    t0 = time.time()
    counts = {}
    with open(a.log, "a") as log, ProcessPoolExecutor(a.jobs) as ex:
        if new_log:
            log.write("\t".join(LOG_COLS) + "\n")
        futs = {ex.submit(process, os.path.join(a.src_dir, n), os.path.join(a.dst_dir, n),
                          sums.get(n) if sums else None): n for n in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            log.write("\t".join(str(r[k]).replace("\t", " ").replace("\n", " ") for k in LOG_COLS) + "\n")
            log.flush()
            if r["status"] != "OK" or i % 250 == 0 or i == len(todo):
                print(f"[{i}/{len(todo)}] {time.time() - t0:.0f}s {counts} last={r['file']} {r['status']} {r['error']}",
                      flush=True)
    print(f"done in {time.time() - t0:.1f}s: {counts}", flush=True)
    return 0 if set(counts) <= {"OK"} else 1


def cmd_scan(a):
    names = sorted(n for n in os.listdir(a.src_dir) if n.endswith(".parquet"))
    keys = {}
    hits = {}
    bad = 0
    with open(a.out, "w") as out:
        out.write("file\tfooter_len\troundtrip_identical\tkv_keys\torganis_paths\n")
        for n in names:
            p = os.path.join(a.src_dir, n)
            try:
                _, _, flen, footer = read_footer(p)
                meta = parse_footer(footer)
                rt = encode(meta) == footer
                ks = [k for k, _ in kv_pairs(meta)]
                ps = [path for path, s in walk_strings(meta) if PROBE in s.lower()]
            except Exception as e:  # noqa: BLE001
                out.write(f"{n}\t\tERROR {e}\t\t\n")
                bad += 1
                continue
            bad += not rt
            for k in ks:
                keys[k] = keys.get(k, 0) + 1
            for path in ps:
                hits[path] = hits.get(path, 0) + 1
            out.write(f"{n}\t{flen}\t{rt}\t{','.join(ks)}\t{','.join(ps)}\n")
    print(json.dumps({"files": len(names), "roundtrip_or_parse_failures": bad, "kv_keys": keys,
                      "organis_paths": hits}, indent=1))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan"); s.add_argument("src_dir"); s.add_argument("out")
    o = sp.add_parser("one"); o.add_argument("src"); o.add_argument("dst")
    r = sp.add_parser("run"); r.add_argument("src_dir"); r.add_argument("dst_dir"); r.add_argument("log")
    r.add_argument("--jobs", type=int, default=8); r.add_argument("--sums"); r.add_argument("--only", nargs="*")
    r.add_argument("--trust-log", action="store_true", help="skip logged OK files without re-hashing them")
    c = sp.add_parser("content"); c.add_argument("src"); c.add_argument("dst")
    a = ap.parse_args()
    if a.cmd == "scan":
        return cmd_scan(a)
    if a.cmd == "one":
        print(json.dumps(write_renamed(a.src, a.dst), indent=1))
        return 0
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "content":
        r = content_check(a.src, a.dst)
        print(json.dumps({k: (str(v) if isinstance(v, tuple) else v) for k, v in r.items()}, indent=1))
        return 0 if r["equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
