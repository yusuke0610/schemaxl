# schemaxl

**Schema-first declarative Excel reports for Python**

**Pydantic モデルを単一の真実(Single Source of Truth)として、Excel 帳票を宣言的に生成する Python ライブラリ。**

> ⚠️ **ステータス: 骨格のみ (skeleton).** 本リポジトリは現時点でディレクトリ構成と API スケッチのみを提供します。制約解決・書き出しロジックは未実装です。

---

## なぜ schemaxl か

Excel 帳票開発は、本質的に厄介な作業を人間に押し付けてきました。

- **画面用グリッドを紙のレイアウトエンジンとして誤用する作業。** セル結合・印刷範囲・改ページ・列幅調整を、人間が手続き的に書いている。
- **曖昧な要件をエンジニアが制約に翻訳する作業。** 帳票要件は「見切れないで」のようなざっくりした望ましさでしか降ってこない。データ量を検証して具体的な制約(折り返す/縮小する/改ページする)に落とす作業が、暗黙のうちにエンジニアへ押し付けられている。

schemaxl は、**データ制約(Pydantic)とレイアウト制約(`Layout`)を型の隣に宣言する**ことで、この翻訳作業をライブラリ側に引き取ります。エンジニアは「何を」書くかを宣言し、「どう」紙に収めるかは制約ソルバに任せます。

さらに、行モデルとレイアウト制約が別の場所に書かれている限り、「`max_length=30` の文字列はこの列幅に収まらない」ことは誰も事前に検証できません。schemaxl は両者が型の隣に同居しているため、**レンダリング前の静的検証**(実データすら不要)が可能になります。

## 2 行で帳票にする

DuckDB(や任意のクエリ結果)を、そのまま帳票へ。

```python
import duckdb
from myapp.reports import AllergyReport

# fetchall() はタプルのリストを返す。SELECT の列順を AllergyRow の
# フィールド宣言順に合わせておけば、位置マップでそのまま渡せる。
rows = duckdb.sql("SELECT child_name, allergens FROM allergy_list WHERE grade = 3").fetchall()
AllergyReport.render(rows, "report.xlsx")
```

### `render` の入力契約

`Report.render(rows, path)` が受け取れるのは以下の 2 種類(MVP スコープ):

1. **dict のリスト** — キーがフィールド名にマップされる(基本形)。

   ```python
   AllergyReport.render(
       [{"child_name": "山田 太郎", "allergens": ["卵", "乳"]}],
       "report.xlsx",
   )
   ```

2. **タプル / リストのリスト** — モデルの**フィールド宣言順**で位置マップされる。
   `duckdb.sql(...).fetchall()` の結果(タプルのリスト)はこちらに該当する。

いずれの場合も、渡された行は内部で `AllergyRow` に変換され、Pydantic の
データ制約(`max_length` 等)で検証されてからレンダリングされる。

## API スケッチ

> 以下は設計の完成イメージです。**まだ動作しません**(骨格のみ)。

```python
from typing import Annotated
from pydantic import BaseModel, Field
from schemaxl import Report, Table, Layout, A4, Auto, Fill, Wrap, Shrink, mm

class AllergyRow(BaseModel):
    child_name: Annotated[
        str,
        Field(max_length=30),                                             # データ制約
        Layout(header="児童名", width=Auto(min=mm(30)), overflow=Wrap()),  # レイアウト制約
    ]
    allergens: Annotated[
        list[str],
        Layout(header="アレルゲン", width=Fill, join="、", overflow=Shrink(min_pt=8)),
    ]

class AllergyReport(Report[AllergyRow]):
    page = A4(orientation="portrait", margin=mm(15))
    body = Table(break_inside="avoid_row", repeat_header=True)
```

- `Field(...)` は **データ制約**(Pydantic 本来の役割)。
- `Layout(...)` は **レイアウト制約**。`Annotated` によって型の隣に同居させ、単一の真実に統合する。
- `width` … `Auto(min=...)`(内容に応じ自動、下限指定可)/ `Fill(min=...)`(残り幅を埋める、下限指定可)。
  引数なしなら `Fill` / `Fill()` どちらでも可(内部でインスタンスに正規化)。残り幅が下限に
  満たない構成は `LayoutError`(幅 0 の列を黙って作らない)。
- `overflow` … 収まらないときの戦略。`Wrap()`(折り返し)/ `Shrink(min_pt=...)`(フォント縮小、下限 pt 指定)。引数なしの戦略は `Wrap` / `Wrap()` どちらでも可(内部でインスタンスに正規化)。
- `break_inside="avoid_row"` … 1 行の途中でページを割らない。
- `repeat_header=True` … ヘッダ行を各ページの先頭で繰り返す。
- **行モデルは `Report[AllergyRow]` のジェネリクスから推論される**ため、`Table(bind=...)` は省略できる(同じ情報を 2 回書かない)。明示したい場合は `Table(bind=AllergyRow)` も可。

## アーキテクチャ

schemaxl は「制約を解く純粋関数」と「紙に書き出す副作用」を明確に分離します。

```
Pydantic モデル(単一の真実)
  → 制約解決(列幅計算・行高計算・改ページ位置決定) ※純粋関数群
  → 配置計画(どのセルに何を書くかの中間表現 = PlacementPlan)
  → 物理書き出し(openpyxl バックエンド)
```

| 層 | モジュール | 役割 |
| --- | --- | --- |
| モデル | `core/model.py` | `Layout` メタデータ、`Report` / `Table` 定義 |
| 単位 | `core/units.py` | `mm`, `pt` などの単位型 |
| overflow 戦略 | `core/overflow.py` | `Wrap`, `Shrink` 等の収まらないときの戦略 |
| 制約解決 | `core/solver.py` | 列幅・行高・改ページの解決(**純粋関数**) |
| 配置計画 | `core/plan.py` | 配置計画の中間表現 `PlacementPlan` |
| バックエンド | `backends/openpyxl_backend.py` | `PlacementPlan` → xlsx 書き出し |

この分離により、ソルバ層はファイル I/O なしで単体テストでき(`tests/test_solver.py`)、バックエンドは差し替え可能になります。

## ディレクトリ構成

```
schemaxl/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── src/
│   └── schemaxl/
│       ├── __init__.py             # 公開 API を re-export (Report, Table, Layout, A4, Auto, Fill, Wrap, Shrink, mm)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── model.py            # Layout メタデータ、Report / Table 定義
│       │   ├── units.py            # mm, pt などの単位型
│       │   ├── overflow.py         # Wrap, Shrink 等の overflow 戦略
│       │   ├── solver.py           # 制約解決(列幅・行高・改ページ)※純粋関数群
│       │   └── plan.py             # 配置計画の中間表現(PlacementPlan)
│       └── backends/
│           ├── __init__.py
│           └── openpyxl_backend.py # PlacementPlan → xlsx 書き出し
├── tests/
│   ├── __init__.py
│   ├── test_solver.py              # 制約解決層のテスト置き場(空の骨格)
│   └── test_overflow.py
└── examples/
    └── allergy_report.py           # README のスケッチを動かす想定の example(骨格)
```

## インストール(将来)

```bash
pip install schemaxl
```

開発版:

```bash
pip install -e ".[dev]"
```

## Roadmap

### MVP (v0.1)

- [x] `Table`(単一テーブルの帳票)
- [x] overflow 戦略: `Wrap`(折り返し)/ `Shrink`(フォント縮小、下限 pt 指定)
- [x] A4 縦・自動改ページ(`break_inside="avoid_row"`)
- [x] ヘッダ行の各ページ繰り返し
- [x] openpyxl バックエンド

### 将来構想

- [ ] 制約の静的検証(`schemaxl check`): `max_length` と列幅・overflow 戦略を突き合わせ、破綻しうる組み合わせをレンダリング前に検出
- [ ] `Block` のネスト・複数ブロック配置(Sheet → Block → Item 階層)
- [ ] overflow 戦略の追加: `Ellipsis`(省略記号)/ `SplitBlock`(2 ブロック展開)
- [ ] データプロファイリング(実データ / DB スキーマから制約違反を事前検出しレポート)
- [ ] 極端ケースデータの自動生成(`max_length` ぴったり等)+ スナップショットテスト支援
- [ ] 帳票仕様書(Markdown)の自動生成
- [ ] バックエンドの追加(LibreOffice / PDF 等)

## ライセンス

MIT
