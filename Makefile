# Makefile of the cregit token dataset v1.
#
# Run the targets in the dev shell: nix develop, then make <target>.
# A target that cannot work yet prints "not ready: <reason>" and exits with a non-zero status.
# REPRODUCE.md describes each stage.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# The directory of the downloaded published files (the dataset release).
DATA_DIR ?= data/published
# The directory of the tool bundles of tools.lock.
TOOLS_DIR ?= tools/bundles
PROJECT ?=

.PHONY: help verify rebuild-one select build merge validate stage-hashes test sync-check flake-check

help:
	@echo "Reviewer targets:"
	@echo "  make verify                        check the sha256 of the published files (DATA_DIR=$(DATA_DIR))"
	@echo "  make rebuild-one PROJECT=<name>    build one project again and compare it (REPRODUCE.md, section 6.1)"
	@echo "Stage targets:"
	@echo "  make select      selection (S1-S6)"
	@echo "  make build       the dataset build (S7), all projects"
	@echo "  make merge       join the per-project files"
	@echo "  make validate    check the column contract of the published files"
	@echo "Repository checks:"
	@echo "  make stage-hashes check the copied stage outputs against their recorded sha256"
	@echo "  make test        run the tests of the copied scripts"
	@echo "  make sync-check  check the copied files against sync/sources.tsv and sync/untracked.tsv"
	@echo "  make flake-check run nix flake check (the tool identity check on x86_64-linux)"

verify:
	@scripts/verify.sh "$(DATA_DIR)"

rebuild-one:
	@if [ -z "$(PROJECT)" ]; then echo "usage: make rebuild-one PROJECT=<owner__repo>" >&2; exit 2; fi
	@DATA_DIR="$(DATA_DIR)" scripts/rebuild-one.sh "$(PROJECT)" "$(TOOLS_DIR)"

select:
	@echo "not ready: S1-S3 read live APIs and web pages (GitHub, GitLab hosts, rosters), and the offline replay of S4-S6 from the copied inputs is not written yet; pipeline/SELECTION-STAGES.md gives the steps" >&2; exit 3

build:
	@echo "not ready: the full dataset build runs on EC2 for several days (estimate: about US\$$1,600-1,800); the runner scripts of the EC2 machines are in pipeline/s7-run/runner/, one kit for each run, with no single entry point; use make rebuild-one for one project" >&2; exit 3

merge:
	@echo "not ready: the final merge script is not written yet; pipeline/s7-run/prelim_merge.py is a preliminary view over local run directories" >&2; exit 3

validate:
	@scripts/validate.sh "$(DATA_DIR)"

stage-hashes:
	@scripts/check-stage-hashes.sh

# The runner copies (pipeline/s7-run/runner/) are not run here: their tests need the run kit
# layout and the rendered tokens.
test:
	@if [ -z "$${CREGIT_PYTHON:-}" ]; then echo "not ready: CREGIT_PYTHON is not set (run in the dev shell: nix develop)" >&2; exit 3; fi
	@for d in pipeline/s5-evidence pipeline/s6-labels pipeline/s7-run; do \
	  echo "== $$d"; (cd $$d && PYTHONDONTWRITEBYTECODE=1 "$$CREGIT_PYTHON" -I -m pytest -q -p no:cacheprovider --ignore=runner .); \
	done

sync-check:
	@sync/sync-from-sources.sh --check

flake-check:
	nix flake check -L
