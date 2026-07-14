"""Layout メタデータ、Report / Table 定義、ページ / 幅の指定。

- Layout:  Annotated 内で型の隣に置くレイアウト制約メタデータ。
- Auto / Fill: 列幅の指定。
- A4:      ページ設定。
- Report:  帳票の宣言基底クラス(ジェネリック)。
- Table:   単一テーブルのボディ定義。

本ファイルは骨格。制約解決や書き出しはここでは行わない(solver / backend が担当)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, get_args, get_type_hints

from schemaxl.core.overflow import OverflowStrategy, normalize
from schemaxl.core.units import Length

RowT = TypeVar("RowT")

# render が受け付ける 1 行の入力(MVP スコープ)。
# - dict:      キーがフィールド名にマップされる
# - Sequence:  モデルのフィールド宣言順で位置マップされる(タプル / リスト)
RowInput = dict[str, Any] | Sequence[Any]


# --- 列幅の指定 -----------------------------------------------------------


class Width:
    """列幅指定の基底。"""


@dataclass(frozen=True)
class Auto(Width):
    """内容に応じて自動決定する。min で下限を指定できる。"""

    min: Length | None = None


@dataclass(frozen=True)
class _Fill(Width):
    """行の残り幅を埋める。"""


# `width=Fill` のようにシングルトンとして使う。
Fill: _Fill = _Fill()


# --- レイアウト制約メタデータ ---------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Annotated 内でフィールドに付与するレイアウト制約。

    例::

        child_name: Annotated[str, Field(...), Layout(header="児童名", width=Auto())]
    """

    header: str
    width: Width | None = None
    # 引数なし戦略はクラス参照でも可(overflow.normalize で正規化)。
    overflow: OverflowStrategy | type[OverflowStrategy] | None = None
    join: str | None = None  # list 値を 1 セルへ結合する際の区切り文字


# --- ページ設定 -----------------------------------------------------------


@dataclass(frozen=True)
class A4:
    """A4 ページ設定。"""

    orientation: Literal["portrait", "landscape"] = "portrait"
    margin: Length | None = None


# --- ボディ定義 -----------------------------------------------------------


@dataclass
class Table:
    """単一テーブルのボディ定義。

    各フィールドの Layout から列を構成する。行モデルは通常 `Report[RowT]` の
    ジェネリクスから推論されるため、`bind` は省略可能。明示したい場合のみ
    Pydantic モデルを渡す。
    """

    bind: type[Any] | None = None
    break_inside: Literal["avoid_row", "auto"] = "avoid_row"
    repeat_header: bool = True


# --- 列(モデルから抽出した solver 向けの中間表現)-----------------------


@dataclass(frozen=True)
class Column:
    """モデルの 1 フィールドから抽出した列定義。

    Annotated 内の `Layout` を読み取り、solver が参照しやすい形へ正規化したもの。
    overflow はここでインスタンスへ正規化済み(`Wrap` / `Wrap()` の差を吸収)。
    """

    index: int
    field_name: str
    header: str
    width: Width
    overflow: OverflowStrategy | None
    join: str | None


def columns_of(model: type[Any]) -> list[Column]:
    """Pydantic モデル(等)のフィールド宣言順に `Column` を抽出する。

    各フィールドの `Annotated[..., Layout(...)]` から列を構成する。Layout が
    付いていないフィールドは列にしない。width 省略時は `Auto()`、overflow は
    `overflow.normalize` でインスタンスへ正規化する。
    """
    hints = get_type_hints(model, include_extras=True)
    columns: list[Column] = []
    index = 0
    for name, hint in hints.items():
        if not hasattr(hint, "__metadata__"):
            continue
        layout = next((m for m in get_args(hint)[1:] if isinstance(m, Layout)), None)
        if layout is None:
            continue
        overflow = normalize(layout.overflow) if layout.overflow is not None else None
        width = layout.width if layout.width is not None else Auto()
        columns.append(Column(index, name, layout.header, width, overflow, layout.join))
        index += 1
    return columns


def cell_text(column: Column, row: Any) -> str:
    """1 セルに表示する文字列を得る。dict / モデルインスタンスの両方に対応。

    list 値は `Layout.join`(未指定なら "、")で 1 セルへ結合する。
    """
    value = (
        row.get(column.field_name)
        if isinstance(row, dict)
        else getattr(row, column.field_name, None)
    )
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        separator = column.join if column.join is not None else "、"
        return separator.join(str(item) for item in value)
    return str(value)


# --- 帳票の宣言基底 -------------------------------------------------------


class Report(Generic[RowT]):
    """帳票の宣言基底クラス。

    サブクラスで page(A4 等)と body(Table)をクラス属性として宣言する::

        class AllergyReport(Report[AllergyRow]):
            page = A4(orientation="portrait", margin=mm(15))
            body = Table(bind=AllergyRow)
    """

    page: A4
    body: Table

    @classmethod
    def render(cls, rows: list[RowInput], path: str) -> None:
        """rows を帳票化して path (xlsx) に書き出す。

        rows は dict のリスト(キー → フィールド名)またはタプル / リストの
        リスト(フィールド宣言順で位置マップ)を受け付ける。各行は内部で
        行モデルへ変換され、Pydantic のデータ制約で検証される。

        パイプライン: モデル → solver(制約解決)→ PlacementPlan → backend(書き出し)。
        骨格のため未実装。
        """
        raise NotImplementedError
