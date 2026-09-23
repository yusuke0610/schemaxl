# Changelog

このプロジェクトの主な変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、
バージョンは [PEP 440](https://peps.python.org/pep-0440/) に従う。

各 PR は `Unreleased` に追記し、リリース時に `v<version>` の見出しへ移す
(タグ `v<version>` と `schemaxl.__version__` が一致しないとリリースワークフローが止まる)。

## [Unreleased]

### Added

- CI でカバレッジを計測し、層ごとの閾値(core 95% / backends 85%)を課す
- CI で sdist / wheel をビルドし `twine check` を通す
- `v*` タグの push で PyPI へ公開するリリースワークフロー(Trusted Publishing)
- Dependabot(pip / GitHub Actions)と、`flake.lock` の週次更新ワークフロー
- PR テンプレートと issue テンプレート(不具合報告 / 機能要望)

### Changed

- dev 依存の ruff / mypy をマイナーバージョンまで固定した(更新は Dependabot の PR 経由)

## [0.1.0.dev0]

### Added

- MVP: 単一 `Table` の帳票、overflow 戦略 `Wrap` / `Shrink`、A4 縦・自動改ページ
  (`break_inside="avoid_row"`)、ヘッダ行の各ページ繰り返し、openpyxl バックエンド
