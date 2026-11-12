# Makefile of the dataset Token on Me (TOM) 1.1.0 (and 1.0.0) and of its build.
#
# Run the targets in the dev shell: nix develop, then make <target>.
# A target that cannot work yet prints "not ready: <reason>" and exits with a non-zero status.
# REPRODUCE.md describes each stage.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# The directory of the downloaded published files (the dataset release).
DATA_DIR ?= data/published
# The checksum list of make verify (data/SHA256SUMS-1.0.0: the root of TOM 1.0.0).
SUMS ?= data/SHA256SUMS
# The directory of the tool bundles of tools.lock.
TOOLS_DIR ?= tools/bundles
PROJECT ?=

.PHONY: help verify rebuild-one select build merge validate stage-hashes test sync-check flake-check

help:
	@echo "Reviewer targets:"
	@echo "  make verify                        check the sha256 of the published files (DATA_DIR=$(DATA_DIR), SUMS=$(SUMS))"
	@echo "  make rebuild-one PROJECT=<name>    build one project again and compare it (REPRODUCE.md, section 6.1)"
	@echo "Stage targets:"
	@echo "  make select      selection (S1-S6)"
	@echo "  make build       the dataset build (S7), all projects"
	@echo "  make merge       join the per-project files"
	@echo "  make validate    check the 53 columns of TOM (SCHEMA=2: the source root, 71 columns)"
	@echo "Repository checks:"
	@echo "  make stage-hashes check the copied stage outputs and the release pass kits against their recorded sha256"
	@echo "  make test        run the tests of the copied scripts and of scripts/"
	@echo "  make sync-check  check the copied files against sync/sources.tsv and sync/untracked.tsv"
	@echo "  make flake-check run nix flake check (the tool identity check on x86_64-linux)"

verify:
	@SUMS="$(SUMS)" scripts/verify.sh "$(DATA_DIR)"

rebuild-one:
	@if [ -z "$(PROJECT)" ]; then echo "usage: make rebuild-one PROJECT=<owner__repo>" >&2; exit 2; fi
	@DATA_DIR="$(DATA_DIR)" scripts/rebuild-one.sh "$(PROJECT)" "$(TOOLS_DIR)"

select:
	@echo "not ready: S1-S3 read live APIs and web pages (GitHub, GitLab hosts, rosters), and the offline replay of S4-S6 from the copied inputs is not written yet; pipeline/SELECTION-STAGES.md gives the steps" >&2; exit 3

build:
	@echo "not ready: the full dataset build runs on EC2 for several days (estimate: about US\$$1,600-1,800); the runner scripts of the EC2 machines are in pipeline/s7-run/runner/, one kit for each run, with no single entry point; use make rebuild-one for one project" >&2; exit 3

merge:
	@echo "not ready: the layer merge (pipeline/s7-run/final_merge.py) reads the run files from private storage, and the release write needs the salt, which is deleted by design; make rebuild-one does the merge step for one project" >&2; exit 3

validate:
	@scripts/validate.sh "$(DATA_DIR)"

stage-hashes:
	@scripts/check-stage-hashes.sh
	@steps/release-passes/check-kits.sh

# The runner copies (pipeline/s7-run/runner/) are not run here: their tests need the run kit
# layout and the rendered tokens.
test:
	@if [ -z "$${CREGIT_PYTHON:-}" ]; then echo "not ready: CREGIT_PYTHON is not set (run in the dev shell: nix develop)" >&2; exit 3; fi
	@for d in pipeline/s5-evidence pipeline/s6-labels pipeline/s7-run scripts; do \
	  echo "== $$d"; (cd $$d && PYTHONDONTWRITEBYTECODE=1 "$$CREGIT_PYTHON" -I -m pytest -q -p no:cacheprovider --ignore=runner .); \
	done
	@# The tests of steps/ run with an empty home folder: the tests that read local inputs
	@# (a pseudonymizer checkout, the work folders of the run host) skip (steps/README.md). Exit
	@# status 5 of pytest (no test ran: all of a folder skipped) counts as a pass.
	@h=$$(mktemp -d); trap 'rm -r "$$h"' EXIT; \
	for t in steps/organizations/study/s8-companies:. steps/final-write:test steps/final-write/added-project:test \
	         steps/release-root:"test measure/test fill-release/test" steps/release-passes/fill-release:test; do \
	  d=$${t%%:*}; echo "== $$d"; (cd $$d && HOME=$$h PYTHONDONTWRITEBYTECODE=1 "$$CREGIT_PYTHON" -I -m pytest -q -p no:cacheprovider $${t#*:}) || \
	    [ $$? -eq 5 ]; \
	done

sync-check:
	@sync/sync-from-sources.sh --check

flake-check:
	nix flake check -L
