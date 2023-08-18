{
  description = "eshet.py";

  inputs = {
    utils.url = "github:numtide/flake-utils";

    yarp_src.url = "github:tomjnixon/yarp/time_window";
    yarp_src.flake = false;
  };

  outputs = { self, nixpkgs, utils, yarp_src }:
  utils.lib.eachSystem utils.lib.defaultSystems (system:
    let
      pkgs = nixpkgs.legacyPackages."${system}";
      python = pkgs.python3;
    in rec {
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

      packages.eshet_py = python.pkgs.buildPythonPackage rec {
        name = "eshet";
        format = "flit";
        src = ./.;
        propagatedBuildInputs = with python.pkgs; [
          msgpack
          sentinel
          packages.yarp
        ];
        pythonImportsCheck = [ "eshet" ];
      };

      defaultPackage = packages.eshet_py;
    }
    );
}
