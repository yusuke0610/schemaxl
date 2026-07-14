# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの現状

**骨格 (skeleton) 段階。** 公開 API のシグネチャ・型・docstring は揃っているが、
実処理はほぼすべて `raise NotImplementedError` のまま。ここでの主な作業は
「未実装の純粋関数を、既存の型シグネチャと docstring の契約どおりに埋めていく」こと。
新しい API を足す前に、README.md の「API スケッチ」節が設計の意図の一次情報である点に注意。

## 開発コマンド

Nix + direnv 前提の環境。`.envrc` で `use flake` しているため、`direnv allow` 済みなら
devShell の Python(pydantic / openpyxl / pytest / mypy / ruff 入り)が自動で有効になる。
direnv を使わない場合は `nix develop` に入るか、`pip install -e ".[dev]"` する。

```bash
pytest                       # テスト実行
pytest tests/test_solver.py  # 単一ファイル
pytest tests/test_solver.py::test_resolve_page_breaks_avoid_row  # 単一テスト

ruff check .                 # lint
ruff format --check .        # フォーマット検証(CI と同じ)
ruff format .                # フォーマット適用
mypy                         # 型チェック(strict。packages=["schemaxl"] を対象)
```

CI(`.github/workflows/ci.yml`)は Python 3.10 / 3.11 / 3.12 で
`ruff check` → `ruff format --check` → `mypy` → `pytest` の順に回す。
`mypy` は `strict = true`、`ruff` は `line-length = 100`。この 4 つを緑にすることがマージ条件。

現状テストは `@pytest.mark.skip("骨格")` で全スキップ。solver を実装したら対応する
skip を外して有効化する運用。

## アーキテクチャ

核となる設計判断は **「制約を解く純粋関数」と「紙に書き出す副作用」の分離**。
データは一方向に流れる:

```
Pydantic モデル(単一の真実)
  → solver(列幅・行高・改ページを解決)      ※純粋関数・I/O なし
  → PlacementPlan(どのセルに何を書くかの中間表現)  ※出力ライブラリ非依存の純データ
  → openpyxl backend(唯一の副作用境界)      ※レイアウト判断は一切しない
```

この分離を壊さないことが最重要:
- **solver 層(`core/solver.py`)にファイル I/O や openpyxl を持ち込まない。** 純粋性が
  `tests/test_solver.py` での I/O レス単体テストを成立させている。
- **backend(`backends/openpyxl_backend.py`)にレイアウト判断を書かない。** 幅・高さ・
  改ページはすべて solver が決定済みという前提で、`PlacementPlan` を機械的に xlsx へ写すだけ。
- **`PlacementPlan`(`core/plan.py`)を openpyxl 非依存に保つ。** これがバックエンド差し替え
  (将来の LibreOffice / PDF)の境界。

### 各モジュールの役割

| 層 | モジュール | 役割 |
| --- | --- | --- |
| モデル | `core/model.py` | `Layout` メタデータ、`Report` / `Table` / `A4`、`Auto` / `Fill`、`render` エントリ |
| 単位 | `core/units.py` | `mm` / `pt` → `Length` 値オブジェクト(内部基準単位は pt 予定) |
| overflow | `core/overflow.py` | `Wrap` / `Shrink` と、クラス参照→インスタンスの `normalize` |
| solver | `core/solver.py` | `resolve_column_widths` / `resolve_row_heights` / `resolve_page_breaks` / `solve` |
| 計画 | `core/plan.py` | `PlacementPlan`(`CellPlacement` / `PageBreak`) |
| backend | `backends/openpyxl_backend.py` | `write_xlsx(plan, path)` |

### ドメインの中心概念

- **データ制約とレイアウト制約を型の隣に同居させる。** `Annotated[str, Field(max_length=30),
  Layout(header="児童名", width=Auto(), overflow=Wrap())]` のように、Pydantic の `Field`
  (データ制約)と `schemaxl` の `Layout`(レイアウト制約)を 1 つの型注釈に並べる。これが
  「単一の真実」であり、将来の静的検証(`max_length` と列幅の突き合わせ)の土台。
- **行モデルは `Report[RowT]` のジェネリクスから推論する。** `Table(bind=...)` は明示したい
  ときだけ。同じ情報を二度書かせない設計なので、推論経路を壊さないこと。
- **`render` の入力契約**(`core/model.py` の `RowInput`):dict のリスト(キー→フィールド名)
  か、Sequence のリスト(モデルのフィールド宣言順で位置マップ。`duckdb.fetchall()` 由来の
  タプル列がこれ)。どちらも内部で行モデルへ変換し Pydantic 検証を通してからレンダリングする。
- **overflow は「収まらないとき」の戦略。** `Wrap()`(折り返して行高を伸ばす)/
  `Shrink(min_pt=...)`(フォント縮小、下限あり)。引数なし戦略はクラス参照でも受け付け、
  `overflow.normalize` で必ずインスタンスへ正規化してから solver が参照する。

## 実装を進めるときの順序の目安

依存の下流(値オブジェクト)から埋めると型が通りやすい:
`units.py`(`Length.to_pt` / `mm` / `pt`)→ `overflow.normalize` → solver の各 `resolve_*`
→ `solve` で `PlacementPlan` 組み立て → backend の `write_xlsx`。
スコープは README の Roadmap「MVP (v0.1)」に定義済み(単一 `Table` / `Wrap` + `Shrink` /
A4 縦・自動改ページ / ヘッダ繰り返し / openpyxl)。それ以外は「将来構想」であり MVP では作らない。
