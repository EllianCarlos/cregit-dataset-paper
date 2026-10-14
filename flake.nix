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
  #   packages.devenv         the devenv command of the dataset build (devenv 2.4.0)
  #   packages.cregit-jars    the 4 cregit jars that the pipeline runs, in the directory
  #                           layout of a cregit checkout (fixed-output files, see below)
  #   packages.default        srcml, cregit-perl, cregit-python, git and sqlite in one environment
  #   devShells.default       the shell for the Makefile targets (with devenv)
  #   checks.tools            the tools run (each system)
  #   checks.srcml-identity   srcML, python3, the cregit perl and python environments and git
  #                           must have the store paths of the dataset build, and libsrcml its
  #                           sha256 (x86_64-linux only, see below)
  #   checks.devenv-identity  devenv must have the store path of the dataset build
  #                           (x86_64-linux only)
  #
  # The cregit jars (blobExec, slickGitLog, persons, remapCommits): sbt downloads their
  # dependencies at build time, so they are not pure Nix builds. This flake pins the jar
  # files of the dataset build by sha256 with requireFile. The jar files are in the tool
  # bundle set (jars/ with jars/SHA256SUMS). Add the files to the Nix store before you build
  # packages.cregit-jars:
  #   nix-store --add-fixed sha256 jars/*.jar
  # The devShell and the checks do not need the jars.
  #
  # ctp runs every cregit step through "devenv shell" from the fixed path
  # ~/.nix-profile/bin/devenv. The devShell puts devenv on PATH. For ctp, also install it
  # into the profile: nix profile add .#devenv
  description = "cregit token dataset v1: pinned tools and environment";

  inputs = {
    # Same rev as the "nixpkgs" node of tools/cregit/devenv.lock.
    nixpkgs.url = "github:cachix/devenv-nixpkgs/256551e45f6303e142ab4a98be1bf243feb77dc0";
    # The nixpkgs of the devenv command of the dataset build. The run machines installed
    # devenv with "nix profile add nixpkgs#devenv". Their profile manifest records this
    # locked URL (NixOS/nixpkgs 39ad350a0602fa0a58a544344e3e9187526ea45c).
    nixpkgs-devenv.url = "https://releases.nixos.org/nixpkgs/nixpkgs-26.11pre1087089.39ad350a0602/nixexprs.tar.zst?narHash=sha256-/4ezBOv6aldGab7qTb6ls3SDpgzG8kuuSqEAA9zEZ8E%3D";
  };

  outputs = { self, nixpkgs, nixpkgs-devenv }:
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
        # The same path on the local machine and on the three EC2 machines that ran on 2026-10-14.
        devenvOutPath = "/nix/store/5sbcspxmvsj6g41dmv20flpvj9v8pzi8-devenv-2.4.0";
      };

      # The cregit jars that run_pipeline_process.sh runs, with their path in a cregit
      # checkout. The sha256 values are of the jar files of the local runs (tools.lock).
      # Each run machine built its own jars. The blobExec jar has the same sha256 on all
      # machines that were checked. The other three jars have the same entries (name, CRC-32,
      # size) on those machines; only the zip time stamps of their nested jar differ
      # (tools/jars/jar_content_sha256.py).
      cregitJars = [
        { dir = "blobExec/target/scala-2.13"; name = "blobExec-0.1.0-assembly.jar";
          sha256 = "3daa120111958bce27d296308ea8341a377312712371baa9b3ba6dccdc43ad16"; }
        { dir = "slickGitLog/target/scala-2.10"; name = "slickgitlog_2.10-0.1-SNAPSHOT-one-jar.jar";
          sha256 = "da2d2c3698c0efd0845f1eb675f392ae059b6e093f3cbeee76663948f828b394"; }
        { dir = "persons/target/scala-2.10"; name = "persons_2.10-0.1-SNAPSHOT-one-jar.jar";
          sha256 = "327392b672546c7e244a6b30c756b378ce71106d5d216819486d9b55e57a5462"; }
        { dir = "remapCommits/target/scala-2.10"; name = "remapcommits_2.10-0.1-SNAPSHOT-one-jar.jar";
          sha256 = "a8e2865d4ae4d3851e57ee18e9dff5c697f570369d869651b62e2bc54c1de2aa"; }
      ];

      jarsFor = pkgs:
        let
          jarFile = j: pkgs.requireFile {
            inherit (j) name sha256;
            # requireFile sets "unfree" by default. The cregit code is GPL-3.0-or-later (its
            # COPYING file). The jars also hold their dependencies, under their own licenses.
            meta.license = pkgs.lib.licenses.gpl3Plus;
            message = ''
              ${j.name} is not in the Nix store. Get it from the tool bundle set
              (jars/${j.name}, listed in jars/SHA256SUMS). Then add it:
                nix-store --add-fixed sha256 ${j.name}
            '';
          };
        in
        # The jars in the directory layout of a cregit checkout. To use them, copy them into
        # the checkout: cp -rL --no-preserve=mode result/. <cregit checkout>/
        pkgs.runCommand "cregit-jars" { } (pkgs.lib.concatMapStrings (j: ''
          mkdir -p $out/${j.dir}
          ln -s ${jarFile j} $out/${j.dir}/${j.name}
        '') cregitJars);

      # The devenv command of the dataset build, for each system.
      devenvFor = system: nixpkgs-devenv.legacyPackages.${system}.devenv;

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
          # tools/ctp-venv/ gives the package lists of the run venvs.
          ctp-python = pkgs.python312.withPackages (ps: [ ps.duckdb ps.pytest ps.coverage ]);
        in
        { inherit srcml cregit-perl cregit-python ctp-python; };
    in
    {
      packages = forAllSystems (system: pkgs:
        let t = toolsFor pkgs; in
        t // {
          devenv = devenvFor system;
          cregit-jars = jarsFor pkgs;
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
              # The command that ctp runs for each cregit step ("devenv shell").
              (devenvFor system)
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
            # The cregit python environment by its full path. "python3" on PATH is the bare
            # interpreter (git-filter-repo brings it) with PYTHONPATH set, as in the devenv
            # shell. "python3 -I" ignores PYTHONPATH, so scripts use CREGIT_PYTHON instead.
            CREGIT_PYTHON = "${t.cregit-python}/bin/python3";
            shellHook = ''
              echo "cregit dataset shell (${system}). Run: make help"
            '';
          };
        });

      checks = forAllSystems (system: pkgs:
        let t = toolsFor pkgs; devenv = devenvFor system; in
        {
          # The tools build on each system.
          tools = pkgs.runCommand "cregit-dataset-tools-check" { } ''
            ${t.srcml}/bin/srcml --version
            ${t.cregit-perl}/bin/perl -MDBI -MDBD::SQLite -MSet::Scalar -MHTML::FromText -e 'print "perl modules: ok\n"'
            ${t.cregit-python}/bin/python3 -c 'import duckdb; print("cregit duckdb", duckdb.__version__)'
            ${t.ctp-python}/bin/python3 -c 'import duckdb; print("ctp duckdb", duckdb.__version__)'
            ${devenv}/bin/devenv --version
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
          # The devenv command must be the same store path as on the run machines.
          devenv-identity = pkgs.runCommand "devenv-identity-check" { } ''
            set -eu
            test "${devenv}" = "${build.devenvOutPath}" || { echo "devenv: ${devenv}, want ${build.devenvOutPath}"; exit 1; }
            echo "devenv matches the dataset build"
            touch $out
          '';
        });
    };
}
