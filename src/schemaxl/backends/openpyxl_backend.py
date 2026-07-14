"""openpyxl バックエンド。

PlacementPlan を受け取り、openpyxl で .xlsx を書き出す。
ここが唯一の副作用境界であり、レイアウト判断は一切行わない
(幅・高さ・改ページはすべて solver が決定済みの前提)。
"""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break

from schemaxl.core.plan import PlacementPlan


def write_xlsx(plan: PlacementPlan, path: str) -> None:
    """PlacementPlan を path の .xlsx として書き出す。

    - column_widths / row_heights を反映
    - CellPlacement を書き込み(結合セル・フォント pt・折り返しを適用)
    - page_breaks / 印刷タイトル行(repeat_header)を反映
    """
    workbook = Workbook()
    worksheet = workbook.active

    for cell in plan.cells:
        target = worksheet.cell(row=cell.row, column=cell.col, value=cell.value)
        if cell.font_pt is not None:
            target.font = Font(size=cell.font_pt)
        target.alignment = Alignment(wrap_text=cell.wrap, vertical="top")
        if cell.row_span > 1 or cell.col_span > 1:
            worksheet.merge_cells(
                start_row=cell.row,
                start_column=cell.col,
                end_row=cell.row + cell.row_span - 1,
                end_column=cell.col + cell.col_span - 1,
            )

    for col, width in plan.column_widths.items():
        worksheet.column_dimensions[get_column_letter(col)].width = width

    for row, height in plan.row_heights.items():
        worksheet.row_dimensions[row].height = height

    # PageBreak.before_row は「その行の直前で改ページ」。openpyxl の Break(id=N) は
    # 「行 N の直後で改ページ」なので id = before_row - 1。
    for page_break in plan.page_breaks:
        worksheet.row_breaks.append(Break(id=page_break.before_row - 1))

    # 印刷タイトル行(各ページ先頭でヘッダを繰り返す)。
    if plan.header_rows > 0:
        worksheet.print_title_rows = f"1:{plan.header_rows}"

    workbook.save(path)
