"""DP8L, the license rule (decided 2026-10-10, SELECTION-STAGES.md section 6): one rule for all hosts.

The project has a license file at the snapshot commit, read from the root tree: a root file whose name is
LICENSE, LICENCE, LICENSES, UNLICENSE or COPYING, alone or followed by '.', '-', '_', a space or a digit
(case-insensitive; for example LICENSE.txt, LICENSE-MIT, COPYING3), or a root folder named LICENSES,
LICENCES, LICENSE or LICENCE that holds at least one file (REUSE). A source or build file (licenses.cpp,
license.json) is not a license file. Final DP8L (user, 2026-10-10 ~01:40 UTC): this root rule, OR, for GitHub rows,
a license that GitHub detects (pool column license not empty); funnel.py --dp8l applies the union.
"""
import re

LICENSE_FILE = re.compile(r"^((un)?licen[cs]es?|copying)([-._ 0-9].*)?$", re.I)
LICENSE_DIR = re.compile(r"^licen[cs]es?$", re.I)
CODE_EXT = re.compile(r"\.(c|cc|cpp|cxx|h|hh|hpp|hxx|java|kt|rs|py|go|js|ts|json|ya?ml|xml|qrc|toml|cmake|sh|gradle|"
                      r"properties|ui|proto)$", re.I)


def is_license_file(name):
    """A root file (blob) that counts."""
    return bool(LICENSE_FILE.match(name)) and not CODE_EXT.search(name)


def is_license_dir(name):
    """A root folder name that counts if the folder holds at least one file."""
    return bool(LICENSE_DIR.match(name))


def is_license_name(name):
    """For a root listing without entry types (git ls-tree --name-only, clone_facts.py): the name is a license
    file or a license folder name. Git keeps no empty folder, so a listed folder holds at least one entry."""
    return is_license_file(name) or is_license_dir(name)
