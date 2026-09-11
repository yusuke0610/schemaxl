"""単位型。

帳票レイアウトはミリメートル (mm) とポイント (pt) が混在する。
内部基準単位は **pt** に統一し、`Length.to_pt()` で正規化する。

solver が openpyxl バックエンドへ渡す際は、さらに「Excel の列幅単位・行高単位」へ
変換する必要がある。その変換係数はマジックナンバーにせず、本モジュールの定数
(`PT_PER_COLUMN_WIDTH_UNIT`)に一元化する。
"""

from __future__ import annotations

from dataclasses import dataclass

# 1 inch = 25.4 mm = 72 pt。この 2 つの定義から他の係数を導く。
PT_PER_INCH = 72.0
MM_PER_INCH = 25.4
PT_PER_MM = PT_PER_INCH / MM_PER_INCH

# Excel の列幅は「標準フォントの文字数」で表される特殊な単位。
# 目安として 1 文字ぶんの幅 ≒ 96dpi で 7 デバイス px。
# 96dpi 上の 7px を pt へ直すと 7 * 72/96 = 5.25 pt。
# 実フォント計測に踏み込まず、この近似係数を単位変換の一次情報として一元管理する。
_DEVICE_DPI = 96.0
_PX_PER_COLUMN_WIDTH_UNIT = 7.0
PT_PER_COLUMN_WIDTH_UNIT = _PX_PER_COLUMN_WIDTH_UNIT * PT_PER_INCH / _DEVICE_DPI  # = 5.25

_UNIT_TO_PT = {"mm": PT_PER_MM, "pt": 1.0}


@dataclass(frozen=True)
class Length:
    """長さを表す値オブジェクト。内部基準単位は pt。

    負の長さは存在しないため生成時に拒否する(mm(0) / pt(0) は有効)。
    比較・加算は物理的な長さ(pt 換算)で行うため、単位が違っても意味のある
    大小比較ができる(改ページ計算での高さ累積に用いる)。
    """

    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in _UNIT_TO_PT:
            raise ValueError(f"未知の単位: {self.unit!r}(mm または pt)")
        if self.value < 0:
            raise ValueError(f"長さに負値は指定できない: {self.value}{self.unit}")

    def to_pt(self) -> float:
        """ポイントへ変換する。"""
        return self.value * _UNIT_TO_PT[self.unit]

    def __add__(self, other: Length) -> Length:
        if not isinstance(other, Length):
            return NotImplemented
        # 同一単位なら単位を保ったまま、異なるなら pt へ正規化して返す。
        if self.unit == other.unit:
            return Length(self.value + other.value, self.unit)
        return Length(self.to_pt() + other.to_pt(), "pt")

    def __lt__(self, other: Length) -> bool:
        if not isinstance(other, Length):
            return NotImplemented
        return self.to_pt() < other.to_pt()

    def __le__(self, other: Length) -> bool:
        if not isinstance(other, Length):
            return NotImplemented
        return self.to_pt() <= other.to_pt()

    def __gt__(self, other: Length) -> bool:
        if not isinstance(other, Length):
            return NotImplemented
        return self.to_pt() > other.to_pt()

    def __ge__(self, other: Length) -> bool:
        if not isinstance(other, Length):
            return NotImplemented
        return self.to_pt() >= other.to_pt()


def mm(value: float) -> Length:
    """ミリメートル指定の長さを返す。負値は ValueError。"""
    return Length(value, "mm")


def pt(value: float) -> Length:
    """ポイント指定の長さを返す。負値は ValueError。"""
    return Length(value, "pt")


def pt_to_excel_row_height(value_pt: float) -> float:
    """pt を Excel の行高単位へ変換する。行高は pt そのものなので恒等。"""
    return value_pt


def pt_to_excel_column_width(value_pt: float) -> float:
    """pt を Excel の列幅単位(標準フォントの文字数)へ変換する。"""
    return value_pt / PT_PER_COLUMN_WIDTH_UNIT


def pt_to_excel_margin(value_pt: float) -> float:
    """pt を Excel のページ余白単位(インチ)へ変換する。"""
    return value_pt / PT_PER_INCH
