"""Layout メタデータ、Report / Table 定義、ページ / 幅の指定。

- Layout:  Annotated 内で型の隣に置くレイアウト制約メタデータ。
- Auto / Fill: 列幅の指定。
- A4:      ページ設定。
- Report:  帳票の宣言基底クラス(ジェネリック)。
- Table:   単一テーブルのボディ定義。

制約解決や書き出しの実処理はここでは行わない(solver / backend が担当)。
`Report.render` は入力の検証と solver → backend への配線のみを受け持つ。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Generic, Literal, TypeVar, get_args, get_origin, get_type_hints

from schemaxl.core.errors import LayoutError
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
class Fill(Width):
    """行の残り幅を埋める。min で下限を指定できる。

    下限を割り込む構成は solver が `LayoutError` にする。幅 0 の列を黙って作ると、
    折り返しが 1 文字ずつに退化した帳票が出てしまうため。
    """

    min: Length | None = None


def normalize_width(width: Width | type[Width]) -> Width:
    """列幅指定を常にインスタンスへ正規化する。

    `width=Fill`(クラス参照)も `width=Fill()` も受け付ける。overflow 戦略の
    `overflow.normalize` と同じ扱いに揃えてある。
    """
    if isinstance(width, Width):
        return width
    if isinstance(width, type) and issubclass(width, Width):
        return width()  # 引数なしで構築できる指定のみ成功。
    raise TypeError(f"列幅指定ではない: {width!r}")


# --- レイアウト制約メタデータ ---------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Annotated 内でフィールドに付与するレイアウト制約。

    例::

        child_name: Annotated[str, Field(...), Layout(header="児童名", width=Auto())]
    """

    header: str
    # 引数なしの指定はクラス参照でも可(normalize_width で正規化)。
    width: Width | type[Width] | None = None
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
    width / overflow はここでインスタンスへ正規化済み(`Fill` / `Fill()` の差を吸収)。
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
    付いていないフィールドは列にしない。width 省略時は `Auto()`。width / overflow は
    それぞれ `normalize_width` / `overflow.normalize` でインスタンスへ正規化する。
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
        width = normalize_width(layout.width) if layout.width is not None else Auto()
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


def _field_names(model: type[Any]) -> list[str]:
    """行モデルのフィールド名を宣言順で返す(Sequence 入力の位置マップに使う)。

    Pydantic モデルは `model_fields`(ClassVar 等の非フィールド注釈を含まない)を
    正とし、それ以外は型注釈の宣言順にフォールバックする。
    """
    fields: dict[str, Any] | None = getattr(model, "model_fields", None)
    if fields is not None:
        return list(fields)
    return list(get_type_hints(model))


def _coerce_row(model: type[Any], row: RowInput) -> Any:
    """RowInput 1 件を行モデルへ変換する(Pydantic のデータ制約検証を通す)。"""
    if isinstance(row, dict):
        return model(**row)
    names = _field_names(model)
    if len(row) != len(names):
        raise ValueError(
            f"Sequence 行の要素数 {len(row)} が行モデルのフィールド数 {len(names)} と一致しない"
        )
    return model(**dict(zip(names, row)))


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
    def _row_model(cls) -> type[Any]:
        """行モデルを解決する。`Table.bind` 優先、なければ `Report[RowT]` から推論。"""
        if cls.body.bind is not None:
            return cls.body.bind
        for klass in cls.__mro__:
            for base in getattr(klass, "__orig_bases__", ()):
                if get_origin(base) is Report:
                    arg = get_args(base)[0]
                    if isinstance(arg, type):
                        return arg
        raise LayoutError("Table に行モデルがバインドされていない(bind / Report ジェネリクス)")

    @classmethod
    def render(cls, rows: list[RowInput], path: str) -> None:
        """rows を帳票化して path (xlsx) に書き出す。

        rows は dict のリスト(キー → フィールド名)またはタプル / リストの
        リスト(フィールド宣言順で位置マップ)を受け付ける。各行は内部で
        行モデルへ変換され、Pydantic のデータ制約で検証される。

        パイプライン: モデル → solver(制約解決)→ PlacementPlan → backend(書き出し)。
        """
        # solver は本モジュールへ依存するため、循環 import 回避で遅延 import する。
        from schemaxl.backends.openpyxl_backend import write_xlsx
        from schemaxl.core.solver import solve

        row_model = cls._row_model()
        table = cls.body if cls.body.bind is not None else replace(cls.body, bind=row_model)
        validated = [_coerce_row(row_model, row) for row in rows]
        write_xlsx(solve(cls.page, table, validated), path)
