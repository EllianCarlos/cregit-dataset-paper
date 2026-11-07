#!/usr/bin/env python3
"""hf_tools.py: the Python part of the kit dataset-hf (the TOM dataset on Hugging Face).

Subcommands:
  precheck       the Hub limits against a root (a local folder or an `aws s3 ls --recursive` listing)
  validate-card  the YAML header of the dataset card, checked by the Hub
  create         create the dataset repository if it is missing: PUBLIC by default, --private for a private one;
                 an existing repository of the other visibility is an error (the kit never changes visibility)
  upload         upload a root folder in batches with upload_folder (resumable); the root README.md must be the card
  verify         compare every file of the repository with SHA256SUMS of the root; write hf-verify.txt
  delete-test    delete the test repository (only the name HF_TEST_REPO of hf.conf, private, the expected files)

The token: huggingface_hub reads the file of HF_TOKEN_PATH. This script never reads, prints or logs the token.
Nothing here changes the visibility of a repository or generates a DOI.
"""
import argparse
import hashlib
import sys
import tempfile
import time
from pathlib import Path

TEST_REPO = "elliancarlos/tom-upload-test"
IGNORED_REMOTE = {".gitattributes"}  # the Hub adds this file to each new repository
LOCAL_SKIP_PREFIXES = (".cache/",)   # resume data of older uploaders, never part of the root


def log(msg):
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}", flush=True)


def sha256_file(p, bufsize=8 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def git_blob_sha1(p):
    data = Path(p).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def same_on_hub(r, path, size, sha256):
    if not r or r["size"] != size:
        return False
    if r["lfs_sha256"]:
        return r["lfs_sha256"] == sha256
    return r["blob_id"] == git_blob_sha1(path)  # a small (non-LFS) file: the git blob id


def read_sums(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        name = name.lstrip("*").strip()
        if name in rows:
            raise SystemExit(f"ABORT: {name} twice in {path}")
        rows[name] = digest
    return rows


def api():
    from huggingface_hub import HfApi
    return HfApi()


def hub_version():
    import huggingface_hub
    try:
        import hf_xet  # noqa: F401
        xet = "hf_xet present"
    except ImportError:
        xet = "NO hf_xet"
    return f"huggingface_hub {huggingface_hub.__version__}, {xet}"


def visibility(private):
    return "private" if private else "public"


def require_visibility(a, repo, private):
    info = a.repo_info(repo, repo_type="dataset")
    if bool(info.private) != bool(private):
        raise SystemExit(f"ABORT: {repo} is {visibility(info.private)}, expected {visibility(private)}; "
                         "this kit never changes the visibility")
    return info


def require_card_is_readme(card, sums):
    card_sha = sha256_file(card)
    row = sums.get("README.md")
    if card_sha != row:
        raise SystemExit(f"ABORT: the root README.md ({(row or '-')[:12]} in SHA256SUMS) is not the card "
                         f"{card} ({card_sha[:12]}); copy the card to release-staging/README.md and rebuild")
    return card_sha


def local_files(root):
    root = Path(root)
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if rel.startswith(LOCAL_SKIP_PREFIXES):
                continue
            out[rel] = p.stat().st_size
    return out


def remote_files(a, repo, revision=None):
    files = {}
    for e in a.list_repo_tree(repo, repo_type="dataset", recursive=True, expand=True, revision=revision):
        if e.__class__.__name__ != "RepoFile":
            continue  # a folder
        lfs = getattr(e, "lfs", None)
        files[e.path] = {
            "size": e.size,
            "lfs_sha256": (lfs.sha256 if lfs is not None else None),
            "xet": bool(getattr(e, "xet_hash", None)),
            "blob_id": getattr(e, "blob_id", None),
        }
    return files


def glob_escape(path):
    return "".join("[" + c + "]" if c in "*?[" else c for c in path)


# ------------------------------------------------------------------------------------------------ precheck
def parse_listing(path, marker="/root/"):
    files = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        size, key = int(parts[2]), parts[3]
        i = key.find(marker)
        rel = key[i + len(marker):] if i >= 0 else key
        if rel:
            files[rel] = size
    return files


def cmd_precheck(ns):
    conf = {k: int(v) for k, v in (kv.split("=", 1) for kv in ns.limit)}
    if ns.listing:
        files, src = parse_listing(ns.listing), f"listing {ns.listing}"
    else:
        files, src = local_files(ns.root), f"folder {ns.root}"
    if not files:
        raise SystemExit("ABORT: no files")
    entries = {}
    for rel in files:
        parts = rel.split("/")
        for d in range(len(parts)):
            folder = "/".join(parts[:d]) or "."
            entries.setdefault(folder, set()).add(parts[d])
    total = sum(files.values())
    big_name, big = max(files.items(), key=lambda kv: kv[1])
    fails, warns = [], []
    out = [f"source: {src}", f"visibility of the upload: {ns.visibility}", f"files: {len(files)}",
           f"total bytes: {total} ({total / 1e9:.1f} GB)",
           f"largest file: {big_name} {big} B ({big / 1e9:.2f} GB)", "entries per folder (files and subfolders):"]
    for folder, names in sorted(entries.items(), key=lambda kv: -len(kv[1])):
        mark = ""
        if len(names) > conf["MAX_ENTRIES"]:
            mark = f"  FAIL: more than {conf['MAX_ENTRIES']}"
            fails.append(f"{folder}/ has {len(names)} entries (hard limit {conf['MAX_ENTRIES']} per folder)")
        out.append(f"  {len(names):>7}  {folder}{mark}")
    if big > conf["MAX_FILE"]:
        fails.append(f"largest file {big} B > {conf['MAX_FILE']} B (hard limit)")
    elif big > conf["REC_FILE"]:
        warns.append(f"largest file {big} B > {conf['REC_FILE']} B (recommended)")
    if len(files) > conf["REC_FILES"]:
        warns.append(f"{len(files)} files > {conf['REC_FILES']} (recommended)")
    if ns.visibility == "private":
        quota, plan = ns.quota, "given"
        if quota == "auto":
            try:
                w = api().whoami()
                pro = bool(w.get("isPro"))
                plan = f"{w.get('name')}, {'PRO' if pro else 'free'} account"
                quota = conf["PRO"] if pro else conf["FREE"]
            except Exception as e:  # no token: no quota check
                plan, quota = f"unknown ({e.__class__.__name__})", None
        quota = int(quota) if quota is not None else None
        out.append(f"private storage quota: {quota if quota is not None else 'not checked'} B ({plan})")
        if quota is not None and total > quota:
            fails.append(f"total {total} B > the private quota {quota} B ({plan})")
    else:
        out.append("repository size: no per-repository limit; public storage of a free account is best-effort "
                   "(the Hub asks for responsible use beyond a few GB, and a contact for TBs of data)")
        if total > conf["PUBLIC_NOTE"]:
            warns.append(f"total {total} B > {conf['PUBLIC_NOTE']} B: a large public dataset; the Hub asks for a "
                         "dataset card, Parquet files and the repository limits (all met when this check passes)")
    out.append(f"limits: entries per folder <= {conf['MAX_ENTRIES']} (hard), file <= {conf['MAX_FILE']} B (hard), "
               f"file < {conf['REC_FILE']} B and files < {conf['REC_FILES']} (recommended)")
    for w in warns:
        out.append(f"WARN: {w}")
    for f in fails:
        out.append(f"FAIL: {f}")
    out.append("PRECHECK " + ("FAIL" if fails else "PASS"))
    text = "\n".join(out) + "\n"
    print(text, end="")
    if ns.out:
        Path(ns.out).write_text(text)
    return 1 if fails else 0


# ------------------------------------------------------------------------------------------------ card
def cmd_validate_card(ns):
    from huggingface_hub import DatasetCard
    card = DatasetCard.load(ns.card)
    card.validate(repo_type="dataset")
    data = card.data.to_dict()
    log(f"card valid: pretty_name={data.get('pretty_name')!r} license={data.get('license')!r} "
        f"configs={[c.get('config_name') for c in data.get('configs', [])]}")
    return 0


# ------------------------------------------------------------------------------------------------ create
def cmd_create(ns):
    a = api()
    if a.repo_exists(ns.repo, repo_type="dataset"):
        require_visibility(a, ns.repo, ns.private)
        log(f"{ns.repo}: exists, {visibility(ns.private)}")
        return 0
    a.create_repo(ns.repo, repo_type="dataset", private=bool(ns.private), exist_ok=False)
    require_visibility(a, ns.repo, ns.private)
    log(f"{ns.repo}: created, {visibility(ns.private)}")
    return 0


# ------------------------------------------------------------------------------------------------ upload
def cmd_upload(ns):
    a = api()
    log(hub_version())
    require_visibility(a, ns.repo, ns.private)
    root = Path(ns.root)
    sums_path = root / "SHA256SUMS"
    sums = read_sums(sums_path)
    loc = local_files(root)
    if set(loc) != set(sums) | {"SHA256SUMS"}:
        miss = sorted(set(sums) - set(loc))[:5]
        extra = sorted(set(loc) - set(sums) - {"SHA256SUMS"})[:5]
        raise SystemExit(f"ABORT: the root does not match its SHA256SUMS (missing {miss}, extra {extra})")
    if ns.card:
        require_card_is_readme(ns.card, sums)
        if sha256_file(root / "README.md") != sums["README.md"]:
            raise SystemExit("ABORT: the root README.md does not match its SHA256SUMS row")
        log(f"the root README.md is the card ({sums['README.md'][:12]})")
    want = dict(sums)
    want["SHA256SUMS"] = sha256_file(sums_path)
    remote = remote_files(a, ns.repo)
    todo = [rel for rel in sorted(loc) if not same_on_hub(remote.get(rel), root / rel, loc[rel], want[rel])]
    log(f"root {root}: {len(loc)} files, {sum(loc.values())} B; on the Hub already: {len(loc) - len(todo)}; "
        f"to upload: {len(todo)}")
    # the card (README.md) goes last, so the Hub reads the configs when the data files are there
    todo.sort(key=lambda r: r == "README.md")
    batches, cur, cur_b = [], [], 0
    for rel in todo:
        if cur and (len(cur) >= ns.batch_files or cur_b + loc[rel] > ns.batch_bytes or rel == "README.md"):
            batches.append(cur)
            cur, cur_b = [], 0
        cur.append(rel)
        cur_b += loc[rel]
    if cur:
        batches.append(cur)
    t0, sent = time.time(), 0
    for k, batch in enumerate(batches, 1):
        nb = sum(loc[r] for r in batch)
        tb = time.time()
        a.upload_folder(repo_id=ns.repo, repo_type="dataset", folder_path=str(root),
                        allow_patterns=[glob_escape(r) for r in batch],
                        commit_message=f"TOM 1.0.0: batch {k} of {len(batches)} ({len(batch)} files)")
        sent += nb
        el = time.time() - t0
        log(f"batch {k}/{len(batches)}: {len(batch)} files, {nb} B in {time.time() - tb:.0f} s; "
            f"total {sent} B in {el:.0f} s ({sent / max(el, 1) / 1e6:.1f} MB/s)")
    require_visibility(a, ns.repo, ns.private)
    log(f"UPLOAD DONE {ns.repo} ({visibility(ns.private)}): {len(batches)} batches, {sent} B")
    return 0


# ------------------------------------------------------------------------------------------------ verify
def cmd_verify(ns):
    from huggingface_hub import hf_hub_download
    a = api()
    info = a.repo_info(ns.repo, repo_type="dataset")
    rev = info.sha
    sums = read_sums(ns.sums)
    want = dict(sums)
    want["SHA256SUMS"] = sha256_file(ns.sums)
    lines, bad = [], 0
    notes = []
    if ns.card:
        card_sha = sha256_file(ns.card)
        if card_sha == sums.get("README.md"):
            notes.append(f"README.md: the SHA256SUMS row is the card {ns.card} ({card_sha[:12]})")
        else:
            bad += 1
            lines.append(f"CARD: the SHA256SUMS row of README.md ({sums.get('README.md', '-')[:12]}) is not the card "
                         f"{ns.card} ({card_sha[:12]})")
    remote = remote_files(a, ns.repo, revision=rev)
    ignored = sorted(set(remote) & IGNORED_REMOTE)
    for p in ignored:
        remote.pop(p)
    missing = sorted(set(want) - set(remote))
    extra = sorted(set(remote) - set(want))
    for p in missing:
        lines.append(f"MISSING {p}")
    for p in extra:
        lines.append(f"EXTRA {p}")
    bad += len(missing) + len(extra)
    n_lfs = n_small = 0
    n_xet = sum(1 for r in remote.values() if r["xet"])
    with tempfile.TemporaryDirectory(prefix="hf-verify-") as tmp:
        for p in sorted(set(want) & set(remote)):
            r = remote[p]
            if r["lfs_sha256"]:
                n_lfs += 1
                got, how = r["lfs_sha256"], "lfs"
            else:
                n_small += 1
                f = hf_hub_download(ns.repo, p, repo_type="dataset", revision=rev, local_dir=tmp)
                got, how = sha256_file(f), "download"
            if got != want[p]:
                bad += 1
                lines.append(f"DIFFERENT {p} ({how}): hub {got} want {want[p]}")
    head = [f"repository: {ns.repo} (dataset), revision {rev}, {visibility(info.private)}",
            f"reference: {ns.sums} ({len(sums)} rows, sha256 {want['SHA256SUMS']}) plus SHA256SUMS itself",
            f"files on the Hub: {len(remote)} (not counted: {', '.join(ignored) or 'none'}); expected: {len(want)}",
            f"checked by the LFS/Xet sha256 of the listing: {n_lfs} (Xet-backed: {n_xet}); by download and sha256: {n_small}",
            f"tool: {hub_version()}"] + notes
    if ns.expect in ("public", "private") and visibility(info.private) != ns.expect:
        bad += 1
        lines.append(f"VISIBILITY: the repository is {visibility(info.private)}, expected {ns.expect}")
    verdict = "VERIFY PASS" if bad == 0 else f"VERIFY FAIL: {bad} differences"
    text = "\n".join(head + lines + [verdict]) + "\n"
    if ns.out:
        Path(ns.out).write_text(text)
    print(text, end="")
    return 0 if bad == 0 else 1


# ------------------------------------------------------------------------------------------------ delete-test
def cmd_delete_test(ns):
    if ns.repo != TEST_REPO:
        raise SystemExit(f"ABORT: delete-test deletes only {TEST_REPO}, not {ns.repo}")
    a = api()
    require_visibility(a, ns.repo, True)
    files = sorted(remote_files(a, ns.repo))
    want = sorted(ns.expect)
    if files != want:
        raise SystemExit(f"ABORT: {ns.repo} holds {files}, not the test files {want}; not deleted")
    a.delete_repo(ns.repo, repo_type="dataset")
    log(f"{ns.repo}: deleted (it held only the {len(files)} test files)")
    log(f"exists after: {a.repo_exists(ns.repo, repo_type='dataset')}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("precheck")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--listing")
    g.add_argument("--root")
    s.add_argument("--visibility", choices=("public", "private"), default="public")
    s.add_argument("--quota", default="auto", help="private only: auto (whoami: free or PRO) or bytes")
    s.add_argument("--limit", action="append", default=[],
                   help="NAME=value: MAX_ENTRIES MAX_FILE REC_FILE REC_FILES FREE PRO PUBLIC_NOTE")
    s.add_argument("--out")
    s = sub.add_parser("validate-card")
    s.add_argument("--card", required=True)
    for name in ("create", "upload"):
        s = sub.add_parser(name)
        s.add_argument("--repo", required=True)
        s.add_argument("--private", action="store_true", help="a private repository (default: public)")
        if name == "upload":
            s.add_argument("--root", required=True)
            s.add_argument("--card", help="the card: the root README.md must be this file (by SHA256SUMS)")
            s.add_argument("--batch-files", type=int, default=1000)
            s.add_argument("--batch-bytes", type=int, default=20_000_000_000)
    s = sub.add_parser("verify")
    s.add_argument("--repo", required=True)
    s.add_argument("--sums", required=True)
    s.add_argument("--card")
    s.add_argument("--out")
    s.add_argument("--expect", choices=("public", "private", "any"), default="any", help="the visibility to require")
    s = sub.add_parser("delete-test")
    s.add_argument("--repo", required=True)
    s.add_argument("--expect", action="append", default=[])
    ns = p.parse_args()
    if ns.cmd == "precheck":
        d = {"MAX_ENTRIES": 10000, "MAX_FILE": 500_000_000_000, "REC_FILE": 200_000_000_000,
             "REC_FILES": 100_000, "FREE": 100_000_000_000, "PRO": 1_000_000_000_000,
             "PUBLIC_NOTE": 50_000_000_000}
        d.update(dict(kv.split("=", 1) for kv in ns.limit))
        ns.limit = [f"{k}={v}" for k, v in d.items()]
    fn = {"precheck": cmd_precheck, "validate-card": cmd_validate_card, "create": cmd_create, "upload": cmd_upload,
          "verify": cmd_verify, "delete-test": cmd_delete_test}[ns.cmd]
    sys.exit(fn(ns))


if __name__ == "__main__":
    main()
