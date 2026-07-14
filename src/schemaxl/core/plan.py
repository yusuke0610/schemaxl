"""配置計画の中間表現 (PlacementPlan)。

solver が出力し、backend が消費するデータ構造。
「どのセルに何を、どの書式で書くか」を宣言的に保持する純粋なデータであり、
特定の出力ライブラリ(openpyxl 等)に依存しない。

本ファイルは骨格のためフィールドは暫定。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CellPlacement:
    """1 セル(結合セルを含む)の配置。"""

    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    value: object | None = None
    font_pt: float | None = None
    wrap: bool = False


@dataclass
class PageBreak:
    """改ページ位置。"""

    before_row: int


@dataclass
class PlacementPlan:
    """1 冊分の帳票の配置計画。

    solver の出力。backend はこれを読んで物理ファイルへ書き出す。
    座標は 1 始まりのシート行 / 列。幅は Excel 列幅単位、高さは pt(Excel 行高単位)。
    `dataclasses.asdict` + `json.dumps` で直列化可能な純データに保つ。
    """

    cells: list[CellPlacement] = field(default_factory=list)
    page_breaks: list[PageBreak] = field(default_factory=list)
    column_widths: dict[int, float] = field(default_factory=dict)
    row_heights: dict[int, float] = field(default_factory=dict)
    # 各ページ先頭で繰り返す先頭行数(repeat_header)。印刷タイトル行に対応。
    header_rows: int = 0
