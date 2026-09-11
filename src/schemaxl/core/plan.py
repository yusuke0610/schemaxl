"""配置計画の中間表現 (PlacementPlan)。

solver が出力し、backend が消費するデータ構造。
「どのセルに何を、どの書式で書くか」を宣言的に保持する純粋なデータであり、
特定の出力ライブラリ(openpyxl 等)に依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schemaxl.core.errors import LayoutWarning


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


@dataclass(frozen=True)
class CellRange:
    """セルの矩形範囲(1 始まり・両端を含む)。印刷範囲の表現に使う。"""

    first_row: int
    first_col: int
    last_row: int
    last_col: int


@dataclass(frozen=True)
class PageSetup:
    """ページの物理設定。

    solver はここに載せた用紙・余白を前提に改ページ位置を決めている。backend が
    これを出力ファイルへ写さないと、計算前提と実際の印刷結果が食い違う。

    寸法はすべて **pt**(ライブラリの内部基準単位)で持ち、各バックエンドが
    自分の単位へ変換する(Excel のページ余白はインチ)。ここを Excel 単位に
    しないことが、バックエンド差し替えの境界を保つということ。
    """

    # 用紙の呼称。backend が自分のコード体系へ写す(Excel は paperSize の番号)。
    paper: str
    orientation: str
    # 向きを適用した後の用紙寸法。landscape なら幅 > 高さになる。
    width_pt: float
    height_pt: float
    margin_top_pt: float
    margin_right_pt: float
    margin_bottom_pt: float
    margin_left_pt: float
    # ヘッダ / フッタ領域の高さ。MVP では出力しないので 0。
    header_margin_pt: float = 0.0
    footer_margin_pt: float = 0.0


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
    # 用紙・向き・余白。None なら backend はページ設定に触れない。
    page: PageSetup | None = None
    # 印刷範囲。None なら backend は指定しない(Excel の既定は使用済み範囲)。
    print_area: CellRange | None = None
    # 見切れ等の警告。solver は積むだけで送出しない。扱いは render の strict が決める。
    warnings: list[LayoutWarning] = field(default_factory=list)
