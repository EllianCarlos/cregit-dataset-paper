{
  # The pinned environment of the cregit token dataset v1.
  #
  # The dataset build ran cregit inside its devenv shell. That shell takes its packages
  # from cachix/devenv-nixpkgs at the rev in tools/cregit/devenv.lock. This flake uses
  # the same rev, so it gets the same store paths (python3 3.14.7, duckdb 1.5.5, git
  # 2.55.0, perl, the patched srcML).
  #
  # Outputs, for each system in `systems`:
  #   packages.srcml          srcML d382719 with the non-termination patch (tools/cregit/nix)
  #   packages.cregit-perl    perl with the modules of cregit (copy of devenv.nix perlEnv)
  #   packages.cregit-python  python3 with duckdb and pytest (as in devenv.nix)
  #   packages.ctp-python     python3.12 with duckdb and pytest, for the ctp runner and tests
  #   packages.default        srcml, cregit-perl, cregit-python, git and sqlite in one environment
  #   devShells.default       the shell for the Makefile targets
  #   checks.tools            the tools run (each system)
  #   checks.srcml-identity   srcML, python3, the cregit perl and python environments and git
  #                           must have the store paths of the dataset build, and libsrcml its
  #                           sha256 (x86_64-linux only, see below)
  #
  # Not in this flake yet (REPRODUCE.md, "Left for later"):
  # - the blobExec, persons, remapCommits and slickGitLog jars. sbt downloads their
  #   dependencies at build time, so they are not pure Nix builds. The jar sha256 is in
  #   tools.lock.
  # - the devenv command. ctp runs every cregit step through "devenv shell" from a fixed
  #   path. A rebuild needs that command and a cregit checkout of the pinned commit.
  description = "cregit token dataset v1: pinned tools and environment";

  inputs = {
    # Same rev as the "nixpkgs" node of tools/cregit/devenv.lock.
    nixpkgs.url = "github:cachix/devenv-nixpkgs/256551e45f6303e142ab4a98be1bf243feb77dc0";
  };

  outputs = { self, nixpkgs }:
    let
      # Each output is per system. Only x86_64-linux is tested (see REPRODUCE.md).
      # devenv-nixpkgs applies its patches to nixpkgs in a derivation, at evaluation time.
      # So the outputs of a system evaluate only on that system (or with a builder for it).
      # "nix flake check" checks the current system; "--all-systems" needs those builders.
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system nixpkgs.legacyPackages.${system});

      # The values of the dataset build. They were measured on x86_64-linux only.
      build = {
        system = "x86_64-linux";
        srcmlOutPath = "/nix/store/g6xii595faiacx4yaq4k0k2mrmp3hzhy-srcml-1.1.0-unstable-2026-10-04";
        libsrcmlSha256 = "dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3";
        python3OutPath = "/nix/store/3n4qphl9s728sz8frmpqqrv9b1m87g68-python3-3.14.7";
        cregitPythonOutPath = "/nix/store/5gnikzfb2hkysq9d45mjl74h7vj4c5ad-python3-3.14.7-env";
        cregitPerlOutPath = "/nix/store/kq15zjik5prghj8xl3slaq1crxni4kfb-perl-5.42.0-env";
        gitOutPath = "/nix/store/8wxs6573l730vxkqd6wp58kvxa19csll-git-2.55.0";
      };

      toolsFor = pkgs:
        let
          srcml = pkgs.callPackage ./tools/cregit/nix/srcml.nix { };

          # A copy of the perlEnv of tools/cregit/devenv.nix. Keep the two the same.
          EmailFind = pkgs.perlPackages.buildPerlPackage rec {
            pname = "Email-Find";
            version = "0.10";
            src = pkgs.fetchurl {
              url = "https://cpan.metacpan.org/authors/id/M/MI/MIYAGAWA/Email-Find-0.10.tar.gz";
              sha256 = "sha256-KaqgB9DepKjY23eM8ZHq3sqRxOmIO6So4txNVOjM8g4=";
            };
            propagatedBuildInputs = with pkgs.perlPackages; [ EmailValid ];
            doCheck = false;
            meta.description = "Find email addresses in arbitrary text";
          };
          HTMLFromText = pkgs.perlPackages.buildPerlPackage rec {
            pname = "HTML-FromText";
            version = "2.07";
            src = pkgs.fetchurl {
              url = "https://cpan.metacpan.org/authors/id/R/RJ/RJBS/HTML-FromText-2.07.tar.gz";
              sha256 = "1b93zria8is1kcanwaldyzjcijqcsgrbasvlnmzp1gh584r11q65";
            };
            buildInputs = with pkgs.perlPackages; [ TestMore ];
            propagatedBuildInputs = with pkgs.perlPackages; [ TextAutoformat ] ++ [ EmailFind ];
            doCheck = false;
            meta.description = "Mark up text as HTML";
          };
          cregit-perl = pkgs.perl.withPackages (p: [
            p.DBI
            p.DBDSQLite
            EmailFind
            HTMLFromText
            p.HTMLParser
            p.SetScalar
            p.TextAutoformat
          ]);

          cregit-python = pkgs.python3.withPackages (ps: [ ps.duckdb ps.pytest ]);
          # ctp ran on Python 3.12 (3.12.13 local, 3.12.14 on EC2) with duckdb==1.5.5.
          # ctp.py itself uses the standard library only; duckdb is for its tests and tools.
          ctp-python = pkgs.python312.withPackages (ps: [ ps.duckdb ps.pytest ps.coverage ]);
        in
        { inherit srcml cregit-perl cregit-python ctp-python; };
    in
    {
      packages = forAllSystems (system: pkgs:
        let t = toolsFor pkgs; in
        t // {
          default = pkgs.buildEnv {
            name = "cregit-dataset-tools";
            # ctp-python is not in this environment: its python3 would collide with the
            # python3 of cregit-python. Use packages.ctp-python for it.
            paths = [ t.srcml t.cregit-perl t.cregit-python pkgs.git pkgs.sqlite ];
          };
        });

      devShells = forAllSystems (system: pkgs:
        let t = toolsFor pkgs; in
        {
          default = pkgs.mkShell {
            packages = [
              # The package list of tools/cregit/devenv.nix.
              pkgs.git
              pkgs.gnumake
              pkgs.gcc
              pkgs.sqlite
              pkgs.git-filter-repo
              t.srcml
              pkgs.universal-ctags
              pkgs.xercesc
              pkgs.sbt
              pkgs.jdk21
              t.cregit-perl
              t.cregit-python
              # The tools of the Makefile targets.
              pkgs.coreutils
              pkgs.gnutar
              pkgs.xz
            ];
            SRCML_PREFIX = "${t.srcml}";
            LEGACY_JAVA_HOME = "${pkgs.temurin-bin-8}";
            # The python3 of the ctp runner. It is not on PATH, because python3 on PATH
            # must be the cregit one (as in the devenv shell).
            CTP_PYTHON = "${t.ctp-python}/bin/python3";
            shellHook = ''
              echo "cregit dataset shell (${system}). Run: make help"
            '';
          };
        });

      checks = forAllSystems (system: pkgs:
        let t = toolsFor pkgs; in
        {
          # The tools build on each system.
          tools = pkgs.runCommand "cregit-dataset-tools-check" { } ''
            ${t.srcml}/bin/srcml --version
            ${t.cregit-perl}/bin/perl -MDBI -MDBD::SQLite -MSet::Scalar -MHTML::FromText -e 'print "perl modules: ok\n"'
            ${t.cregit-python}/bin/python3 -c 'import duckdb; print("cregit duckdb", duckdb.__version__)'
            ${t.ctp-python}/bin/python3 -c 'import duckdb; print("ctp duckdb", duckdb.__version__)'
            touch $out
          '';
        } // pkgs.lib.optionalAttrs (system == build.system) {
          # On the system of the dataset build, srcML, python3, the cregit python and perl
          # environments and git must be the same store paths as in the devenv shell of the
          # dataset build, and libsrcml must have the same sha256.
          srcml-identity = pkgs.runCommand "srcml-identity-check" { } ''
            set -eu
            test "${t.srcml}" = "${build.srcmlOutPath}" || { echo "srcml: ${t.srcml}, want ${build.srcmlOutPath}"; exit 1; }
            test "${pkgs.python3}" = "${build.python3OutPath}" || { echo "python3: ${pkgs.python3}, want ${build.python3OutPath}"; exit 1; }
            test "${t.cregit-python}" = "${build.cregitPythonOutPath}" || { echo "cregit-python: ${t.cregit-python}, want ${build.cregitPythonOutPath}"; exit 1; }
            test "${t.cregit-perl}" = "${build.cregitPerlOutPath}" || { echo "cregit-perl: ${t.cregit-perl}, want ${build.cregitPerlOutPath}"; exit 1; }
            test "${pkgs.git}" = "${build.gitOutPath}" || { echo "git: ${pkgs.git}, want ${build.gitOutPath}"; exit 1; }
            got=$(${pkgs.coreutils}/bin/sha256sum ${t.srcml}/lib/libsrcml.so.1.1.0 | ${pkgs.coreutils}/bin/cut -d' ' -f1)
            test "$got" = "${build.libsrcmlSha256}" || { echo "libsrcml: $got, want ${build.libsrcmlSha256}"; exit 1; }
            echo "srcml, python3, cregit-python, cregit-perl, git and libsrcml match the dataset build"
            touch $out
          '';
        });
    };
}
