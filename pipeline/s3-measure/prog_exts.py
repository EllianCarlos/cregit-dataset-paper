"""Extensions that Linguist assigns only to languages of type `programming`."""
import re
from pathlib import Path


def programming_extensions(path=Path(__file__).with_name("languages.yml")):
    types, lang, typ, cur, in_ext = {}, None, None, [], False
    def flush():
        for x in cur:
            types.setdefault(x, set()).add(typ)
    for line in open(path):
        if re.match(r"^[^\s#][^:]*:\s*$", line):
            flush(); lang, typ, cur, in_ext = line[:-2], None, [], False
            continue
        m = re.match(r"^  type: (\w+)", line)
        if m:
            typ = m.group(1)
        if re.match(r"^  extensions:", line):
            in_ext = True; continue
        if in_ext:
            m = re.match(r'^  - "\.(.+)"', line)
            if m:
                cur.append(m.group(1).lower()); continue
            in_ext = False
    flush()
    # An extension counts only if every language that claims it is programming:
    # `.md` is Markdown (prose) as well as GCC Machine Description.
    # The extensions cregit tokenizes always count, whatever else claims them.
    mask = {"c", "c++", "cc", "cp", "cpp", "cxx", "h", "h++", "hh", "hpp", "hxx", "java", "rs", "tcc"}
    return {x for x, t in types.items() if t == {"programming"}} | mask


if __name__ == "__main__":
    e = programming_extensions()
    print(len(e), sorted(x for x in e if x in {"c","h","java","rs","py","js","png","json","md","txt","po","sql","toml","sh","go","kt"}))
