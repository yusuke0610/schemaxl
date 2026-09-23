"""静的検証(`schemaxl.check`)のテスト。

check はデータを使わず、宣言から合成した最悪ケースの行を solver に通すだけの純粋関数。
openpyxl / ファイル I/O なしで検証できる。
"""

from typing import Annotated

from pydantic import BaseModel, Field

from schemaxl import A4, Auto, Fill, Layout, Report, Shrink, Table, Truncate, Wrap, check, mm
from schemaxl.core.check import is_error

PAGE = A4(orientation="portrait", margin=mm(15))


def kinds(report) -> list[str]:
    return [finding.kind for finding in check(report)]


def test_a_report_that_always_fits_has_no_findings() -> None:
    class Row(BaseModel):
        name: Annotated[
            str, Field(max_length=10), Layout(header="名", width=Auto(min=mm(40)), overflow=Wrap())
        ]
        note: Annotated[
            str, Field(max_length=100), Layout(header="備考", width=Fill, overflow=Wrap())
        ]

    class Ok(Report[Row]):
        page = PAGE
        body = Table()

    assert check(Ok) == []


def test_shrink_that_cannot_fit_max_length_is_an_error() -> None:
    # 全角 30 文字は min_pt=8 まで縮めても 20mm に収まらない(データ不要で確定する)。
    class Row(BaseModel):
        name: Annotated[
            str,
            Field(max_length=30),
            Layout(header="名", width=Auto(max=mm(20)), overflow=Shrink(min_pt=8)),
        ]

    class Tight(Report[Row]):
        page = PAGE
        body = Table()

    [finding] = check(Tight)
    assert (finding.kind, finding.field_name, finding.col) == ("overflow", "name", 1)
    assert finding.row is None  # 最悪ケースの行はデータではない
    assert finding.overage_pt is not None and finding.overage_pt > 0
    assert is_error(finding)


def test_the_same_shrink_passes_when_max_length_fits() -> None:
    class Row(BaseModel):
        name: Annotated[
            str,
            Field(max_length=5),
            Layout(header="名", width=Auto(max=mm(20)), overflow=Shrink(min_pt=8)),
        ]

    class Fits(Report[Row]):
        page = PAGE
        body = Table()

    assert check(Fits) == []


def test_wrap_taller_than_a_page_is_a_layout_error() -> None:
    # 5mm 幅に全角 3000 文字を折り返すと、1 行でページ印字可能高を超える。
    class Row(BaseModel):
        body: Annotated[
            str,
            Field(max_length=3000),
            Layout(header="本文", width=Auto(max=mm(5)), overflow=Wrap()),
        ]

    class TooTall(Report[Row]):
        page = PAGE
        body = Table()

    [finding] = check(TooTall)
    assert finding.kind == "layout_error"
    assert "ページ印字可能高" in finding.message
    assert is_error(finding)


def test_auto_minimums_wider_than_the_page_are_a_layout_error() -> None:
    class Row(BaseModel):
        a: Annotated[str, Field(max_length=1), Layout(header="A", width=Auto(min=mm(100)))]
        b: Annotated[str, Field(max_length=1), Layout(header="B", width=Auto(min=mm(100)))]

    class TooWide(Report[Row]):
        page = PAGE
        body = Table()

    assert kinds(TooWide) == ["layout_error"]


def test_fill_without_room_is_a_layout_error() -> None:
    class Row(BaseModel):
        a: Annotated[str, Field(max_length=1), Layout(header="A", width=Auto(min=mm(180)))]
        b: Annotated[str, Field(max_length=1), Layout(header="B", width=Fill(min=mm(20)))]

    class NoRoom(Report[Row]):
        page = PAGE
        body = Table()

    assert kinds(NoRoom) == ["layout_error"]


def test_truncation_is_a_warning_not_an_error() -> None:
    class Row(BaseModel):
        note: Annotated[
            str,
            Field(max_length=50),
            Layout(header="備考", width=Auto(max=mm(20)), overflow=Truncate()),
        ]

    class Truncating(Report[Row]):
        page = PAGE
        body = Table()

    [finding] = check(Truncating)
    assert finding.kind == "truncated"
    assert not is_error(finding)


def test_unbounded_text_and_lists_cannot_be_verified() -> None:
    class Row(BaseModel):
        name: Annotated[str, Layout(header="名", width=Fill, overflow=Wrap())]
        maybe: Annotated[str | None, Layout(header="任意", width=Fill, overflow=Wrap())] = None
        tags: Annotated[list[str], Layout(header="タグ", width=Fill, overflow=Wrap())]

    class Unbounded(Report[Row]):
        page = PAGE
        body = Table()

    findings = check(Unbounded)
    assert [(f.kind, f.field_name) for f in findings] == [
        ("unbounded", "name"),
        ("unbounded", "maybe"),
        ("unbounded", "tags"),
    ]
    assert not any(is_error(f) for f in findings)


def test_optional_text_with_max_length_is_verified() -> None:
    class Row(BaseModel):
        name: Annotated[
            str | None,
            Field(max_length=30),
            Layout(header="名", width=Auto(max=mm(20)), overflow=Shrink(min_pt=8)),
        ] = None

    class Tight(Report[Row]):
        page = PAGE
        body = Table()

    assert kinds(Tight) == ["overflow"]


def test_fields_without_layout_are_reported() -> None:
    class Row(BaseModel):
        name: Annotated[str, Field(max_length=5), Layout(header="名")]
        internal_id: int

    class Partial(Report[Row]):
        page = PAGE
        body = Table()

    [finding] = check(Partial)
    assert (finding.kind, finding.field_name) == ("no_layout", "internal_id")
    assert not is_error(finding)


def test_non_text_columns_are_not_worst_cased() -> None:
    class Row(BaseModel):
        qty: Annotated[int, Layout(header="数量", width=Auto(max=mm(5)), overflow=Wrap())]

    class Numbers(Report[Row]):
        page = PAGE
        body = Table()

    assert check(Numbers) == []


def test_the_injected_measure_decides_the_worst_case() -> None:
    # 既定の計測器では収まる宣言でも、文字を 3 倍広く測る計測器では収まらない。
    class Row(BaseModel):
        name: Annotated[
            str,
            Field(max_length=5),
            Layout(header="名", width=Auto(max=mm(20)), overflow=Shrink(min_pt=8)),
        ]

    class Fits(Report[Row]):
        page = PAGE
        body = Table()

    def wide(text: str, font_pt: float) -> float:
        return len(text) * font_pt * 3

    assert check(Fits) == []
    assert [f.kind for f in check(Fits, measure=wide)] == ["overflow"]
