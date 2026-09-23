"""セル値の型と表示文字列のテスト。

`to_cell_value` は純粋関数なので、openpyxl / ファイル I/O なしで検証できる。
表示文字列は幅計測の入力になるため、「Excel が実際に表示する文字列」と一致
(少なくとも短く見積もらない)することをここで固定する。
"""

# Excel の日時はタイムゾーンを持たないので、テストでも naive な datetime を使う
# (fromisoformat で組み立てる)。
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from schemaxl.core.model import Layout
from schemaxl.core.values import check_number_format, to_cell_value


def cv(raw, number_format=None, join="、"):
    return to_cell_value(raw, join=join, number_format=number_format, field_name="f")


# --- 型の保持 -------------------------------------------------------------


def test_int_stays_a_number_not_a_string() -> None:
    value = cv(12)
    assert (value.value, value.kind, value.display) == (12, "number", "12")


def test_float_stays_a_number() -> None:
    value = cv(1234.5)
    assert (value.value, value.kind, value.display) == (1234.5, "number", "1234.5")


def test_bool_is_a_logical_value_displayed_like_excel() -> None:
    # bool は int の派生なので、数値として扱われないこと。
    assert (cv(True).value, cv(True).kind, cv(True).display) == (True, "bool", "TRUE")
    assert cv(False).display == "FALSE"


def test_decimal_is_encoded_as_a_string_to_stay_json_safe() -> None:
    value = cv(Decimal("1234.50"))
    assert (value.value, value.kind, value.display) == ("1234.50", "decimal", "1234.50")


def test_date_gets_a_default_format_and_iso_encoding() -> None:
    value = cv(date(2026, 9, 3))
    assert (value.value, value.kind) == ("2026-09-03", "date")
    assert (value.number_format, value.display) == ("yyyy-mm-dd", "2026-09-03")


def test_datetime_gets_a_default_format_and_iso_encoding() -> None:
    value = cv(datetime.fromisoformat("2026-09-03T08:05:07"))
    assert (value.value, value.kind) == ("2026-09-03T08:05:07", "datetime")
    assert (value.number_format, value.display) == ("yyyy-mm-dd hh:mm:ss", "2026-09-03 08:05:07")


def test_timezone_aware_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="タイムゾーン"):
        cv(datetime(2026, 9, 3, tzinfo=timezone.utc))


def test_none_is_an_empty_cell() -> None:
    value = cv(None)
    assert (value.value, value.display) == (None, "")


def test_list_is_joined_into_text() -> None:
    value = cv(["卵", "乳"], join="/")
    assert (value.value, value.kind, value.display) == ("卵/乳", "text", "卵/乳")


def test_only_text_is_wrappable() -> None:
    assert cv("あ").wrappable
    assert not cv(1).wrappable
    assert not cv(date(2026, 1, 1)).wrappable


# --- number_format と表示文字列 -------------------------------------------


@pytest.mark.parametrize(
    ("raw", "number_format", "display"),
    [
        (1234567, "#,##0", "1,234,567"),
        (1234.5, "#,##0.00", "1,234.50"),
        (Decimal("1234.5"), "#,##0.00", "1,234.50"),
        (-1234567, "#,##0", "-1,234,567"),
        (3.14159, "0.00", "3.14"),
        (42, "0", "42"),
        (0.125, "0.0%", "12.5%"),
        (1, "0%", "100%"),
    ],
)
def test_number_format_drives_the_display_string(raw, number_format, display) -> None:
    value = cv(raw, number_format)
    assert value.display == display
    assert value.number_format == number_format
    assert value.value == (str(raw) if isinstance(raw, Decimal) else raw)


@pytest.mark.parametrize(
    ("raw", "number_format", "display"),
    [
        (date(2026, 9, 3), "yyyy/mm/dd", "2026/09/03"),
        (date(2026, 9, 3), "yyyy/m/d", "2026/9/3"),
        (datetime.fromisoformat("2026-09-03T08:05"), "yyyy/mm/dd hh:mm", "2026/09/03 08:05"),
        (datetime.fromisoformat("2026-09-03T08:05:07"), "hh:mm:ss", "08:05:07"),
    ],
)
def test_date_format_drives_the_display_string(raw, number_format, display) -> None:
    assert cv(raw, number_format).display == display


def test_number_format_does_not_apply_to_text() -> None:
    value = cv("abc", "#,##0")
    assert (value.display, value.number_format) == ("abc", None)


def test_date_format_on_a_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="日付書式"):
        cv(12, "yyyy/mm/dd")


def test_number_format_on_a_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="数値書式"):
        cv(date(2026, 1, 1), "#,##0")


@pytest.mark.parametrize("number_format", ["#,##0", "0.00", "0.0%", "yyyy/mm/dd", "hh:mm"])
def test_supported_formats_pass_the_check(number_format) -> None:
    check_number_format(number_format)


@pytest.mark.parametrize("number_format", ["¥#,##0", "0.00E+00", "[Red]0", "mmm d", "General"])
def test_unsupported_formats_are_rejected_when_the_layout_is_declared(number_format) -> None:
    # 表示を再現できない書式は幅を見積もれないので、Layout の宣言時点で落とす。
    with pytest.raises(ValueError, match="未対応の number_format"):
        Layout(header="金額", number_format=number_format)
