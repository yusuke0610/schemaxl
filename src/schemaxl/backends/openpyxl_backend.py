"""openpyxl バックエンド。

PlacementPlan を受け取り、openpyxl で .xlsx を書き出す。
ここが唯一の副作用境界であり、レイアウト判断は一切行わない
(用紙・余白・幅・高さ・改ページはすべて solver が決定済みの前提)。
"""

from __future__ import annotations

from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break

from schemaxl.backends.base import StrPath
from schemaxl.core.plan import CellRange, PageSetup, PlacementPlan
from schemaxl.core.units import pt_to_excel_margin

# 用紙の呼称 → OOXML の paperSize コード。Excel 固有の符号化であって
# レイアウト判断ではないため、backend 側に置く。
PAPER_SIZE_CODES = {"A4": 9}

# Excel のシート名の制約。Excel 固有の決まりなので backend 側で検査する。
MAX_SHEET_NAME_LENGTH = 31
_FORBIDDEN_SHEET_NAME_CHARS = frozenset("[]:*?/\\")


def _check_sheet_name(name: str) -> None:
    """Excel がシート名として受け付けない名前を ValueError にする。"""
    if not name or len(name) > MAX_SHEET_NAME_LENGTH:
        raise ValueError(f"シート名は 1〜{MAX_SHEET_NAME_LENGTH} 文字: {name!r}({len(name)} 文字)")
    forbidden = sorted(set(name) & _FORBIDDEN_SHEET_NAME_CHARS)
    if forbidden:
        raise ValueError(f"シート名に使えない文字 {''.join(forbidden)!r} を含む: {name!r}")


def _apply_page_setup(worksheet: Any, page: PageSetup) -> None:
    """solver が決めた用紙・向き・余白をシートへ写す。"""
    code = PAPER_SIZE_CODES.get(page.paper)
    if code is None:
        raise ValueError(f"openpyxl バックエンドが知らない用紙: {page.paper!r}")
    worksheet.page_setup.paperSize = code
    worksheet.page_setup.orientation = page.orientation

    # OOXML のページ余白はインチ。
    margins = worksheet.page_margins
    margins.top = pt_to_excel_margin(page.margin_top_pt)
    margins.right = pt_to_excel_margin(page.margin_right_pt)
    margins.bottom = pt_to_excel_margin(page.margin_bottom_pt)
    margins.left = pt_to_excel_margin(page.margin_left_pt)
    # ヘッダ / フッタ領域も明示する。既定の 0.3 inch を残すと、solver が
    # 想定していない余白が本文の上下に入る。
    margins.header = pt_to_excel_margin(page.header_margin_pt)
    margins.footer = pt_to_excel_margin(page.footer_margin_pt)


def _a1_range(area: CellRange) -> str:
    """CellRange を A1 記法("A1:C10")へ変換する。"""
    first = f"{get_column_letter(area.first_col)}{area.first_row}"
    last = f"{get_column_letter(area.last_col)}{area.last_row}"
    return f"{first}:{last}"


def write_xlsx(plan: PlacementPlan, path: StrPath) -> None:
    """PlacementPlan を path の .xlsx として書き出す。

    - sheet_name を反映(Excel のシート名制約に反すれば ValueError)
    - page(用紙・向き・余白)/ print_area を反映
    - column_widths / row_heights を反映
    - CellPlacement を書き込み(結合セル・フォント pt・折り返しを適用)
    - page_breaks / 印刷タイトル行(repeat_header)を反映
    """
    workbook = Workbook()
    worksheet = workbook.active

    if plan.sheet_name is not None:
        _check_sheet_name(plan.sheet_name)
        worksheet.title = plan.sheet_name

    if plan.page is not None:
        _apply_page_setup(worksheet, plan.page)

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

    if plan.print_area is not None:
        worksheet.print_area = _a1_range(plan.print_area)

    workbook.save(path)


class OpenpyxlBackend:
    """openpyxl で .xlsx を書き出す `Backend` 実装。`Report.render` の既定。"""

    def write(self, plan: PlacementPlan, path: StrPath) -> None:
        write_xlsx(plan, path)
