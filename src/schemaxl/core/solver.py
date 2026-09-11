"""制約解決層。

Pydantic モデル + データ行から、列幅・行高・改ページ位置を決定し、
PlacementPlan を構築する。**副作用を持たない純粋関数群**として実装する。

この純粋性が本ライブラリの核。ファイル I/O なしで単体テスト可能
(tests/test_solver.py, tests/test_overflow.py を参照)。

内部計算はすべて **pt** で行い、Excel の単位へは plan 組み立て時(`solve`)に変換する。
文字幅計測は `measure`(実フォント非依存の注入点)を通す。
"""

from __future__ import annotations

from typing import Any

from schemaxl.core.errors import LayoutError
from schemaxl.core.model import A4, Column, Table, cell_text, columns_of
from schemaxl.core.model import Auto as AutoWidth
from schemaxl.core.model import Fill as FillWidth
from schemaxl.core.overflow import DEFAULT_FONT_PT, TextMeasurer, Wrap, default_measure, fit
from schemaxl.core.plan import CellPlacement, CellRange, PageBreak, PageSetup, PlacementPlan
from schemaxl.core.units import mm, pt_to_excel_column_width, pt_to_excel_row_height

# A4 の物理寸法(mm)と呼称。
A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
A4_PAPER_NAME = "A4"

# 行高 = 行内の行数 × フォント pt × この係数(行間)。
LINE_HEIGHT_FACTOR = 1.2

# 列の既定の最小幅。基準フォントの全角 1 文字ぶん。これを下回ると折り返しが
# 1 文字ずつに退化し、帳票として読めなくなる。
MIN_COLUMN_WIDTH_PT = DEFAULT_FONT_PT


def _paper_size_pt(page: A4) -> tuple[float, float]:
    """向きを適用した用紙の物理サイズ(幅, 高さ)を pt で返す。"""
    width_mm, height_mm = A4_WIDTH_MM, A4_HEIGHT_MM
    if page.orientation == "landscape":
        width_mm, height_mm = height_mm, width_mm
    return mm(width_mm).to_pt(), mm(height_mm).to_pt()


def _margin_pt(page: A4) -> float:
    """余白を pt で返す。現状は 4 辺共通で、未指定なら 0。"""
    return page.margin.to_pt() if page.margin is not None else 0.0


def _printable_size_pt(page: A4) -> tuple[float, float]:
    """ページの印字可能サイズ(幅, 高さ)を pt で返す。余白を差し引く。"""
    width_pt, height_pt = _paper_size_pt(page)
    margin_pt = _margin_pt(page)
    return width_pt - 2 * margin_pt, height_pt - 2 * margin_pt


def _page_setup(page: A4) -> PageSetup:
    """ページ設定を backend 非依存の純データへ写す。

    改ページ位置はここで決めた用紙・余白を前提に計算されている。同じ値を必ず
    plan に載せ、backend 側の既定値が使われないようにする(でないと solver の
    計算前提と実際の印刷結果が食い違う)。
    """
    width_pt, height_pt = _paper_size_pt(page)
    margin_pt = _margin_pt(page)
    return PageSetup(
        paper=A4_PAPER_NAME,
        orientation=page.orientation,
        width_pt=width_pt,
        height_pt=height_pt,
        margin_top_pt=margin_pt,
        margin_right_pt=margin_pt,
        margin_bottom_pt=margin_pt,
        margin_left_pt=margin_pt,
    )


def _columns(table: Table) -> list[Column]:
    """table にバインドされた行モデルから列を取り出す。bind 必須。"""
    if table.bind is None:
        raise LayoutError("Table に行モデルがバインドされていない(bind / Report ジェネリクス)")
    return columns_of(table.bind)


def _auto_cap_pt(
    width: AutoWidth, has_overflow: bool, printable_width: float, column_count: int
) -> float | None:
    """Auto 列の内容幅に課す上限 pt。None なら上限なし(内容幅をそのまま使う)。

    `max` の明示が最優先。未指定でも overflow 戦略が宣言されていれば上限を課す。
    課さないと Auto 列は内容が 1 行で収まる幅を常に確保し、Wrap も Shrink も
    発動しないまま終わる。既定の上限は `min`、それも無ければ印字可能幅を列数で
    割った値(Fill 列も頭数に入る粗い見積もりだが、あくまで最後の受け皿)。
    overflow が無い列は切り詰める術がないので、従来どおり内容幅を確保する。
    """
    if width.max is not None:
        return width.max.to_pt()
    if not has_overflow:
        return None
    if width.min is not None:
        return width.min.to_pt()
    return printable_width / column_count


def _fill_min_pt(width: FillWidth) -> float:
    """Fill 列の下限幅 pt。未指定ならライブラリ既定の最小幅。"""
    return width.min.to_pt() if width.min is not None else MIN_COLUMN_WIDTH_PT


def _content_width_pt(column: Column, rows: list[Any], measure: TextMeasurer) -> float:
    """列の内容(ヘッダ + 全行)を 1 行で描いたときの最大幅 pt。"""
    texts = [column.header, *(cell_text(column, row) for row in rows)]
    return max((measure(text, DEFAULT_FONT_PT) for text in texts), default=0.0)


def resolve_column_widths(
    table: Table,
    rows: list[Any],
    page: A4,
    *,
    measure: TextMeasurer = default_measure,
) -> dict[int, float]:
    """各列の幅を pt で決定する(Auto / Fill と min 下限を解決)。

    - Auto:  max(min, min(内容幅, 上限))。上限は `_auto_cap_pt` が決める。
    - Fill:  まず各列へ下限(`Fill.min`、未指定なら `MIN_COLUMN_WIDTH_PT`)を配り、
             残りを等分して上乗せする。下限が等しければ従来どおりの等分になる。
    - Auto 列の合計が印字可能幅を超える → LayoutError(仕様決定1)。
    - Fill 列の下限を賄う残り幅がない → LayoutError。幅 0 の列を黙って作ると、
      折り返しが 1 文字ずつに退化した帳票がそのまま出力されてしまう。
    """
    columns = _columns(table)
    printable_width, _ = _printable_size_pt(page)

    widths: dict[int, float] = {}
    # Fill 指定は幅決定を後回しにする。narrowing を保つため指定も一緒に持つ。
    fill_columns: list[tuple[Column, FillWidth]] = []
    fixed_total = 0.0
    for column in columns:
        if isinstance(column.width, FillWidth):
            fill_columns.append((column, column.width))
            continue
        min_pt = 0.0
        cap_pt: float | None = None
        if isinstance(column.width, AutoWidth):
            if column.width.min is not None:
                min_pt = column.width.min.to_pt()
            cap_pt = _auto_cap_pt(
                column.width, column.overflow is not None, printable_width, len(columns)
            )
        content_pt = _content_width_pt(column, rows, measure)
        if cap_pt is not None:
            content_pt = min(content_pt, cap_pt)
        width = max(min_pt, content_pt)
        widths[column.index] = width
        fixed_total += width

    if fixed_total > printable_width:
        overage = fixed_total - printable_width
        raise LayoutError(
            f"列幅合計 {fixed_total:.1f}pt が印字可能幅 {printable_width:.1f}pt "
            f"を {overage:.1f}pt 超過",
            overage_pt=overage,
        )

    if fill_columns:
        minimums = [_fill_min_pt(spec) for _, spec in fill_columns]
        remaining = printable_width - fixed_total
        required = sum(minimums)
        if remaining < required:
            shortfall = required - remaining
            raise LayoutError(
                f"Fill 列 {len(fill_columns)} 個の最小幅合計 {required:.1f}pt に対し、"
                f"残り幅は {remaining:.1f}pt しかない({shortfall:.1f}pt 不足)",
                overage_pt=shortfall,
            )
        surplus = (remaining - required) / len(fill_columns)
        for (column, _), minimum in zip(fill_columns, minimums):
            widths[column.index] = minimum + surplus

    return widths


def _header_height_pt() -> float:
    """ヘッダ行の高さ(1 行ぶん)。"""
    return DEFAULT_FONT_PT * LINE_HEIGHT_FACTOR


def _cell_height_pt(column: Column, row: Any, width_pt: float, measure: TextMeasurer) -> float:
    """1 セルの高さ pt。overflow 戦略で行数・フォントが決まる。"""
    if column.overflow is None:
        # 戦略未指定は 1 行のまま(Auto 列は内容幅を確保済みなので溢れない)。
        return DEFAULT_FONT_PT * LINE_HEIGHT_FACTOR
    result = fit(
        cell_text(column, row),
        width_pt,
        column.overflow,
        base_font_pt=DEFAULT_FONT_PT,
        measure=measure,
    )
    return result.line_count * result.font_pt * LINE_HEIGHT_FACTOR


def resolve_row_heights(
    table: Table,
    rows: list[Any],
    column_widths: dict[int, float],
    *,
    measure: TextMeasurer = default_measure,
) -> dict[int, float]:
    """overflow 戦略(Wrap / Shrink)を適用して各行の高さを決定する。

    キーはデータ行のインデックス(0 始まり)。行高は行内セルの高さの最大値。
    """
    columns = _columns(table)
    heights: dict[int, float] = {}
    for row_index, row in enumerate(rows):
        heights[row_index] = max(
            (_cell_height_pt(col, row, column_widths[col.index], measure) for col in columns),
            default=DEFAULT_FONT_PT * LINE_HEIGHT_FACTOR,
        )
    return heights


def resolve_page_breaks(table: Table, row_heights: dict[int, float], page: A4) -> list[int]:
    """`break_inside="avoid_row"` を尊重して改ページ位置を決定する。

    戻り値は改ページを入れる直前のデータ行インデックスのリスト。行は途中で割らず、
    収まらない行はページ先頭へ送る。repeat_header 時はヘッダ 1 行ぶんを毎ページ差し引く。
    1 行だけでページに収まらない場合は LayoutError(仕様決定3)。
    """
    _, printable_height = _printable_size_pt(page)
    available = printable_height - (_header_height_pt() if table.repeat_header else 0.0)

    breaks: list[int] = []
    used = 0.0
    for row_index in sorted(row_heights):
        height = row_heights[row_index]
        if height > available:
            overage = height - available
            raise LayoutError(
                f"行 {row_index} の高さ {height:.1f}pt がページ印字可能高 "
                f"{available:.1f}pt を {overage:.1f}pt 超過",
                overage_pt=overage,
                row=row_index,
            )
        if used > 0.0 and used + height > available:
            breaks.append(row_index)
            used = 0.0
        used += height
    return breaks


def _resolved_cell(
    column: Column, row: Any, width_pt: float, measure: TextMeasurer
) -> tuple[str, float, bool]:
    """セルの (表示文字列, 確定フォント pt, 折り返しフラグ) を求める。"""
    text = cell_text(column, row)
    if column.overflow is None:
        return text, DEFAULT_FONT_PT, False
    result = fit(text, width_pt, column.overflow, base_font_pt=DEFAULT_FONT_PT, measure=measure)
    return text, result.font_pt, isinstance(column.overflow, Wrap)


def solve(
    page: A4,
    table: Table,
    rows: list[Any],
    *,
    measure: TextMeasurer = default_measure,
) -> PlacementPlan:
    """制約解決のエントリポイント。PlacementPlan を返す純粋関数。

    列幅・行高・改ページを解決し、シート座標(1 始まり。1 行目ヘッダ、2 行目以降データ)
    へ写して PlacementPlan を組み立てる。幅は Excel 列幅単位、高さは pt へ変換して載せる。
    """
    columns = _columns(table)
    column_widths_pt = resolve_column_widths(table, rows, page, measure=measure)
    row_heights_pt = resolve_row_heights(table, rows, column_widths_pt, measure=measure)
    data_breaks = resolve_page_breaks(table, row_heights_pt, page)

    plan = PlacementPlan(
        header_rows=1 if table.repeat_header else 0,
        page=_page_setup(page),
    )
    header_row = 1

    # ヘッダ行。
    for column in columns:
        plan.cells.append(
            CellPlacement(
                row=header_row,
                col=column.index + 1,
                value=column.header,
                font_pt=DEFAULT_FONT_PT,
                wrap=False,
            )
        )
    plan.row_heights[header_row] = pt_to_excel_row_height(_header_height_pt())

    # データ行。
    for data_index, row in enumerate(rows):
        sheet_row = data_index + 2
        plan.row_heights[sheet_row] = pt_to_excel_row_height(row_heights_pt[data_index])
        for column in columns:
            text, font_pt, wrap = _resolved_cell(
                column, row, column_widths_pt[column.index], measure
            )
            plan.cells.append(
                CellPlacement(
                    row=sheet_row,
                    col=column.index + 1,
                    value=text,
                    font_pt=font_pt,
                    wrap=wrap,
                )
            )

    # 列幅を Excel 単位へ。座標は 1 始まり列。
    for column in columns:
        plan.column_widths[column.index + 1] = pt_to_excel_column_width(
            column_widths_pt[column.index]
        )

    # 改ページ位置をシート行へ変換(データ行 index → シート行)。
    plan.page_breaks = [PageBreak(before_row=data_index + 2) for data_index in data_breaks]

    # 印刷範囲はヘッダ行 + 全データ行 × 全列。列が無ければ指定しない。
    if columns:
        plan.print_area = CellRange(
            first_row=header_row,
            first_col=1,
            last_row=header_row + len(rows),
            last_col=len(columns),
        )

    return plan
