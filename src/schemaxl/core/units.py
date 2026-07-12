"""単位型。

帳票レイアウトはミリメートル (mm) とポイント (pt) が混在する。
内部では単一の基準単位(例: EMU や pt)へ正規化する想定だが、
本ファイルは骨格のため変換ロジックは未実装。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Length:
    """長さを表す値オブジェクト。

    内部表現の基準単位は実装時に確定する(pt を予定)。
    """

    value: float
    unit: str

    def to_pt(self) -> float:
        """ポイントへ変換する。"""
        raise NotImplementedError


def mm(value: float) -> Length:
    """ミリメートル指定の長さを返す。"""
    raise NotImplementedError


def pt(value: float) -> Length:
    """ポイント指定の長さを返す。"""
    raise NotImplementedError
