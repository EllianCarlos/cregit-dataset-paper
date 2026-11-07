# tokei 14.0.0 for measure.py. The script calls the store path directly (TOKEI in measure.py);
# this file records where it comes from: nix-shell -p tokei on 2026-11-07 gave
# /nix/store/m5547wgcn4izfrvm2rvd52f42xrdb00f-tokei-14.0.0.
{ pkgs ? import <nixpkgs> { } }:
pkgs.mkShell { packages = [ pkgs.tokei pkgs.git pkgs.python3 ]; }
