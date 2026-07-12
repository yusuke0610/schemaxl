{
  description = "schemaxl — Pydantic モデルを単一の真実として Excel 帳票を宣言的に生成する";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;

        # ランタイム依存 + 開発ツールをまとめた Python 環境。
        pythonEnv = python.withPackages (ps: with ps; [
          # runtime
          pydantic
          openpyxl
          # dev
          pytest
          mypy
          ruff
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];

          # src レイアウトを editable なしで解決できるようにする。
          shellHook = ''
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
            echo "schemaxl dev shell — $(python --version)"
          '';
        };
      });
}
