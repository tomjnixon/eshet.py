{
  description = "eshet.py";

  inputs = {
    utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, utils }:
  utils.lib.eachSystem utils.lib.defaultSystems (system:
    let
      pkgs = nixpkgs.legacyPackages."${system}";
      python = pkgs.python310;
    in rec {
      packages.eshet_py = python.pkgs.buildPythonPackage rec {
        name = "eshet";
        format = "flit";
        src = ./.;
        propagatedBuildInputs = with python.pkgs; [
          msgpack
          sentinel
        ];
        pythonImportsCheck = [ "eshet" ];
      };

      defaultPackage = packages.eshet_py;
    }
    );
}
