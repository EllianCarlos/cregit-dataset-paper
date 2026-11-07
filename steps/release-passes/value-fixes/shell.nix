{ pkgs ? import <nixpkgs> { } }:
pkgs.mkShell {
  packages = [ pkgs.askalono pkgs.licensee pkgs.python3Packages.scancode-toolkit pkgs.git pkgs.gh pkgs.jq (pkgs.python3.withPackages (ps: [ ps.duckdb ])) ];
}
