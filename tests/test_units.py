"""単位変換のテスト(第1段)。

純 Python で完結する。openpyxl / ファイル I/O には依存しない。

帳票レイアウトは mm と pt が混在するため、内部基準単位 pt へ正規化する。
さらに solver が openpyxl へ渡す際に「Excel の列幅単位・行高単位」へ変換する。
その変換係数はマジックナンバーにせず units モジュールの定数に一元化する。
"""

import math

import pytest

from schemaxl.core.units import (
    PT_PER_COLUMN_WIDTH_UNIT,
    mm,
    pt,
    pt_to_excel_column_width,
    pt_to_excel_row_height,
)

# 1 inch = 25.4 mm = 72 pt という定義から導かれる厳密値。
PT_PER_MM = 72.0 / 25.4


# --- mm / pt → pt --------------------------------------------------------


def test_mm_converts_to_points_by_the_inch_definition() -> None:
    assert mm(25.4).to_pt() == pytest.approx(72.0)


def test_mm_30_is_about_85_04_points() -> None:
    assert mm(30).to_pt() == pytest.approx(30 * PT_PER_MM)


def test_pt_is_identity_to_points() -> None:
    assert pt(11).to_pt() == pytest.approx(11.0)


# --- pt → Excel の単位 ---------------------------------------------------


def test_row_height_is_measured_in_points_so_conversion_is_identity() -> None:
    # Excel の行高はポイントそのもの。
    assert pt_to_excel_row_height(18.0) == pytest.approx(18.0)


def test_column_width_uses_the_shared_conversion_constant() -> None:
    # 列幅は標準フォントの文字数ベース。定数 1 単位ぶんの pt を入れれば 1.0 が返る。
    assert pt_to_excel_column_width(PT_PER_COLUMN_WIDTH_UNIT) == pytest.approx(1.0)
    assert pt_to_excel_column_width(3 * PT_PER_COLUMN_WIDTH_UNIT) == pytest.approx(3.0)


def test_column_width_conversion_constant_is_defined_once_and_positive() -> None:
    # マジックナンバー禁止。係数は 1 箇所の定数として存在し、正の値。
    assert PT_PER_COLUMN_WIDTH_UNIT > 0


# --- 値域 ----------------------------------------------------------------


def test_zero_length_is_valid() -> None:
    assert mm(0).to_pt() == 0.0
    assert pt(0).to_pt() == 0.0


def test_negative_millimeters_raise_value_error() -> None:
    with pytest.raises(ValueError):
        mm(-1)


def test_negative_points_raise_value_error() -> None:
    with pytest.raises(ValueError):
        pt(-0.5)


# --- 比較・加算(改ページ計算での累積のため)-----------------------------


def test_lengths_compare_by_physical_size_across_units() -> None:
    assert mm(10) < mm(20)
    assert mm(30) > pt(10)
    assert pt(72) >= mm(25)


def test_same_unit_addition_preserves_unit_and_value() -> None:
    total = mm(10) + mm(20)
    assert total == mm(30)


def test_cross_unit_addition_normalizes_to_points() -> None:
    total = mm(25.4) + pt(72)
    assert total.to_pt() == pytest.approx(144.0)


def test_length_is_hashable_and_frozen() -> None:
    # 値オブジェクトとして dict キーや set に入れられる。
    assert len({mm(10), mm(10), pt(5)}) == 2
    with pytest.raises(AttributeError):
        mm(10).value = 5  # type: ignore[misc]


def test_addition_of_many_lengths_accumulates() -> None:
    # 改ページ計算では複数の高さを足し込む。
    total = sum((pt(10), pt(20), pt(5)), pt(0))
    assert total.to_pt() == pytest.approx(35.0)
    assert not math.isnan(total.to_pt())
