"""制約解決層のテスト(第3段〜第5段)。

solver は純粋関数なので、ファイル I/O・openpyxl なしで検証できる。
文字幅計測は決定的な計測器を注入し、期待値を環境非依存にする。

このファイルは
  第3段: resolve_column_widths(列幅)
  第4段: resolve_row_heights / resolve_page_breaks(行高・改ページ)
  第5段: solve(PlacementPlan 組み立て・JSON 直列化)
を扱う。
"""

from typing import Annotated

import pytest
from pydantic import BaseModel

from schemaxl.core.errors import LayoutError
from schemaxl.core.model import A4, Auto, Fill, Layout, Table
from schemaxl.core.overflow import Shrink, Wrap
from schemaxl.core.units import mm

# --- 決定的な計測器 -------------------------------------------------------

# A4 縦・余白 15mm の印字可能幅(pt)。テストの期待値計算に使う。
PRINTABLE_WIDTH_PT = mm(210).to_pt() - 2 * mm(15).to_pt()
PAGE = A4(orientation="portrait", margin=mm(15))


def char_measure(text: str, font_pt: float) -> float:
    """1 文字 = font_pt の等幅計測器。"""
    return len(text) * font_pt


def zero_measure(text: str, font_pt: float) -> float:
    """内容幅を 0 とみなす計測器。min / Fill の効果を内容から切り離したいとき用。"""
    return 0.0


# --- 第3段: 列幅解決 -----------------------------------------------------


def test_auto_width_does_not_shrink_below_its_min() -> None:
    class Row(BaseModel):
        name: Annotated[str, Layout(header="名", width=Auto(min=mm(30)))]

    table = Table(bind=Row)
    widths = resolve(table, [{"name": "x"}], measure=zero_measure)
    assert widths[0] == pytest.approx(mm(30).to_pt())


def test_auto_width_grows_to_content_when_larger_than_min() -> None:
    class Row(BaseModel):
        name: Annotated[str, Layout(header="名", width=Auto(min=mm(1)))]

    table = Table(bind=Row)
    # 内容 "abcdefghij" = 10 文字 × 11pt(DEFAULT_FONT_PT)= 110pt > min。
    widths = resolve(table, [{"name": "abcdefghij"}], measure=char_measure)
    assert widths[0] == pytest.approx(10 * 11.0)


def test_fill_column_takes_the_remaining_width() -> None:
    class Row(BaseModel):
        code: Annotated[str, Layout(header="コード", width=Auto(min=mm(30)))]
        note: Annotated[str, Layout(header="備考", width=Fill)]

    table = Table(bind=Row)
    widths = resolve(table, [{"code": "x", "note": "y"}], measure=zero_measure)
    auto = mm(30).to_pt()
    assert widths[0] == pytest.approx(auto)
    assert widths[1] == pytest.approx(PRINTABLE_WIDTH_PT - auto)


def test_multiple_fill_columns_split_the_remaining_width_equally() -> None:
    class Row(BaseModel):
        a: Annotated[str, Layout(header="a", width=Fill)]
        b: Annotated[str, Layout(header="b", width=Fill)]

    table = Table(bind=Row)
    widths = resolve(table, [{"a": "x", "b": "y"}], measure=zero_measure)
    assert widths[0] == pytest.approx(PRINTABLE_WIDTH_PT / 2)
    assert widths[1] == pytest.approx(PRINTABLE_WIDTH_PT / 2)


def test_fixed_columns_exceeding_printable_width_raise_layout_error() -> None:
    # 仕様決定1: 固定(Auto)列の合計が印字可能幅を超えたら LayoutError、
    # 超過量をメッセージ/属性に含める。
    class Row(BaseModel):
        left: Annotated[str, Layout(header="左", width=Auto(min=mm(150)))]
        right: Annotated[str, Layout(header="右", width=Auto(min=mm(150)))]

    table = Table(bind=Row)
    with pytest.raises(LayoutError) as exc:
        resolve(table, [{"left": "x", "right": "y"}], measure=zero_measure)

    expected_overage = 2 * mm(150).to_pt() - PRINTABLE_WIDTH_PT
    assert exc.value.overage_pt == pytest.approx(expected_overage)
    assert "超過" in str(exc.value)


# --- 第4段: 行高解決 -----------------------------------------------------


def test_wrap_row_height_reflects_wrapped_line_count() -> None:
    from schemaxl.core.solver import LINE_HEIGHT_FACTOR, resolve_row_heights

    class Row(BaseModel):
        name: Annotated[str, Layout(header="名", width=Auto(), overflow=Wrap())]

    table = Table(bind=Row)
    # 幅 30pt。char_measure・font 11pt では 1 行 2 文字。5 文字 → 3 行。
    heights = resolve_row_heights(table, [{"name": "あいうえお"}], {0: 30.0}, measure=char_measure)
    assert heights[0] == pytest.approx(3 * 11.0 * LINE_HEIGHT_FACTOR)


def test_shrink_row_height_stays_single_line() -> None:
    from schemaxl.core.solver import LINE_HEIGHT_FACTOR, resolve_row_heights

    class Row(BaseModel):
        code: Annotated[str, Layout(header="コード", width=Auto(), overflow=Shrink(min_pt=1))]

    table = Table(bind=Row)
    # 10 文字 × 11pt = 110pt を幅 50pt へ。font = 11*50/110 = 5pt、1 行。
    heights = resolve_row_heights(table, [{"code": "abcdefghij"}], {0: 50.0}, measure=char_measure)
    assert heights[0] == pytest.approx(1 * 5.0 * LINE_HEIGHT_FACTOR)


def test_row_height_is_the_max_across_columns() -> None:
    from schemaxl.core.solver import LINE_HEIGHT_FACTOR, resolve_row_heights

    class Row(BaseModel):
        tall: Annotated[str, Layout(header="長", width=Auto(), overflow=Wrap())]
        short: Annotated[str, Layout(header="短", width=Auto(), overflow=Wrap())]

    table = Table(bind=Row)
    # tall は 30pt 幅で 3 行、short は広い幅で 1 行 → 行高は 3 行ぶん。
    heights = resolve_row_heights(
        table,
        [{"tall": "あいうえお", "short": "x"}],
        {0: 30.0, 1: 1000.0},
        measure=char_measure,
    )
    assert heights[0] == pytest.approx(3 * 11.0 * LINE_HEIGHT_FACTOR)


# --- 第4段: 改ページ解決 -------------------------------------------------

PRINTABLE_HEIGHT_PT = mm(297).to_pt() - 2 * mm(15).to_pt()


def _one_col_table(repeat_header: bool = True) -> Table:
    class Row(BaseModel):
        name: Annotated[str, Layout(header="名", width=Fill)]

    return Table(bind=Row, repeat_header=repeat_header)


def test_page_break_inserted_before_row_that_would_overflow() -> None:
    from schemaxl.core.solver import resolve_page_breaks

    table = _one_col_table(repeat_header=True)
    header_h = 11.0 * 1.2
    avail = PRINTABLE_HEIGHT_PT - header_h
    h = 0.4 * avail  # 1 ページに 2 行まで
    row_heights = {0: h, 1: h, 2: h, 3: h}
    # row0+row1 = 0.8 ≤ 1、+row2 = 1.2 > 1 → row2 の前で改ページ。
    assert resolve_page_breaks(table, row_heights, PAGE) == [2]


def test_repeat_header_reduces_available_height() -> None:
    from schemaxl.core.solver import resolve_page_breaks

    header_h = 11.0 * 1.2
    # 2 行の合計がヘッダぶんだけ印字可能高を超える高さ。
    h = (PRINTABLE_HEIGHT_PT - header_h) / 2 + 1
    row_heights = {0: h, 1: h}

    # ヘッダ繰り返しありでは収まらず改ページ。
    assert resolve_page_breaks(_one_col_table(repeat_header=True), row_heights, PAGE) == [1]
    # ヘッダぶんが空くと 2 行とも収まり改ページ不要。
    assert resolve_page_breaks(_one_col_table(repeat_header=False), row_heights, PAGE) == []


def test_row_taller_than_page_raises_layout_error() -> None:
    # 仕様決定3: 1 行がページ印字可能高を超える(avoid_row と矛盾)→ LayoutError。
    from schemaxl.core.solver import resolve_page_breaks

    table = _one_col_table(repeat_header=True)
    header_h = 11.0 * 1.2
    avail = PRINTABLE_HEIGHT_PT - header_h
    too_tall = avail + 100.0
    with pytest.raises(LayoutError) as exc:
        resolve_page_breaks(table, {0: too_tall}, PAGE)
    assert exc.value.row == 0
    assert exc.value.overage_pt == pytest.approx(too_tall - avail)
    assert "行 0" in str(exc.value)


# --- 第5段: solve / PlacementPlan ----------------------------------------


class AllergyRow(BaseModel):
    child_name: Annotated[str, Layout(header="児童名", width=Auto(min=mm(30)), overflow=Wrap())]
    allergens: Annotated[
        list[str], Layout(header="アレルゲン", width=Fill, join="、", overflow=Shrink(min_pt=8))
    ]


def _solve_allergy():
    from schemaxl.core.solver import solve

    table = Table(bind=AllergyRow, repeat_header=True)
    rows = [
        {"child_name": "山田", "allergens": ["卵", "乳"]},
        {"child_name": "佐藤", "allergens": ["小麦", "そば"]},
    ]
    return solve(PAGE, table, rows, measure=char_measure)


def test_solve_places_headers_on_the_first_sheet_row() -> None:
    plan = _solve_allergy()
    header_cells = {c.col: c.value for c in plan.cells if c.row == 1}
    assert header_cells == {1: "児童名", 2: "アレルゲン"}


def test_solve_joins_list_values_with_the_configured_separator() -> None:
    plan = _solve_allergy()
    # allergens 列(col 2)の 1 行目データ(row 2)。
    cell = next(c for c in plan.cells if c.row == 2 and c.col == 2)
    assert cell.value == "卵、乳"


def test_solve_marks_wrap_cells_and_not_shrink_cells() -> None:
    plan = _solve_allergy()
    name_cell = next(c for c in plan.cells if c.row == 2 and c.col == 1)
    allergen_cell = next(c for c in plan.cells if c.row == 2 and c.col == 2)
    assert name_cell.wrap is True  # child_name は Wrap
    assert allergen_cell.wrap is False  # allergens は Shrink(折り返さない)


def test_solve_sets_header_rows_for_repeat_header() -> None:
    plan = _solve_allergy()
    assert plan.header_rows == 1


def test_solve_records_column_and_row_dimensions() -> None:
    plan = _solve_allergy()
    # 1 始まり列で列幅を持つ。ヘッダ行 + データ 2 行の高さを持つ。
    assert set(plan.column_widths) == {1, 2}
    assert set(plan.row_heights) == {1, 2, 3}


def test_solve_output_is_json_serializable() -> None:
    import dataclasses
    import json

    plan = _solve_allergy()
    # PlacementPlan は純データ。asdict → json.dumps が通ることを固定する。
    payload = json.dumps(dataclasses.asdict(plan))
    restored = json.loads(payload)
    assert "cells" in restored
    assert "page_breaks" in restored
    assert "header_rows" in restored


# --- ヘルパ ---------------------------------------------------------------


def resolve(table, rows, *, measure):
    from schemaxl.core.solver import resolve_column_widths

    return resolve_column_widths(table, rows, PAGE, measure=measure)
