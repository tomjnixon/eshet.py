{
  description = "eshet.py";

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-24.05";

    utils.url = "github:numtide/flake-utils";

    yarp_src.url = "github:tomjnixon/yarp";
    yarp_src.flake = false;
  };

  outputs = { self, nixpkgs, utils, yarp_src }:
    utils.lib.eachSystem utils.lib.defaultSystems (system:
      let
        pkgs = nixpkgs.legacyPackages."${system}";
        python = pkgs.python3;
      in
      rec {
        packages.yarp = python.pkgs.buildPythonPackage rec {
          name = "yarp";
          format = "setuptools";
          src = yarp_src;
          propagatedBuildInputs = with python.pkgs; [
            sentinel
          ];
          nativeCheckInputs = with python.pkgs; [ pytest pytest-asyncio mock ];
          checkPhase = "pytest";
          pythonImportsCheck = [ "yarp" ];
        };

        packages.asyncio-time-travel = python.pkgs.buildPythonPackage rec {
          pname = "asyncio-time-travel";
          version = "0.3.0";
          format = "setuptools";
          src = python.pkgs.fetchPypi {
            pname = "asyncio_time_travel";
            inherit version;
            sha256 = "sha256-WYmzizQEbocqz5YGmClbC1BTDVWvhhqvJfzilklvniM=";
          };
        };

        packages.eshet_py = python.pkgs.buildPythonPackage rec {
          name = "eshet";
          format = "pyproject";
          src = ./.;
          nativeBuildInputs = with python.pkgs; [ setuptools ];
          propagatedBuildInputs = with python.pkgs; [
            msgpack
            sentinel
            packages.yarp
          ];
          nativeCheckInputs = with python.pkgs; [ pytest pytest-asyncio packages.asyncio-time-travel ];
          checkPhase = "pytest -m 'not needs_server'";
          pythonImportsCheck = [ "eshet" ];
        };

        defaultPackage = packages.eshet_py;

        devShells.eshet_py = packages.eshet_py.overridePythonAttrs (attrs: {
          nativeBuildInputs = attrs.nativeBuildInputs ++ [
            python.pkgs.black
            python.pkgs.flake8
            python.pkgs.pytest-cov
            pkgs.nixpkgs-fmt
          ];
        });

        devShells.default = devShells.eshet_py;
      }
    );
}
