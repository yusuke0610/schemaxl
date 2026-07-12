"""制約解決層。

Pydantic モデル + データ行から、列幅・行高・改ページ位置を決定し、
PlacementPlan を構築する。**副作用を持たない純粋関数群**として実装する。

この純粋性が本ライブラリの核。ファイル I/O なしで単体テスト可能
(tests/test_solver.py, tests/test_overflow.py を参照)。

本ファイルは骨格のためロジックは未実装。
"""

from __future__ import annotations

from typing import Any

from schemaxl.core.model import A4, Table
from schemaxl.core.plan import PlacementPlan


def resolve_column_widths(table: Table, rows: list[Any], page: A4) -> dict[int, float]:
    """各列の幅を決定する(Auto / Fill と min 下限を解決)。"""
    raise NotImplementedError


def resolve_row_heights(
    table: Table, rows: list[Any], column_widths: dict[int, float]
) -> dict[int, float]:
    """overflow 戦略(Wrap / Shrink)を適用して各行の高さを決定する。"""
    raise NotImplementedError


def resolve_page_breaks(
    table: Table, row_heights: dict[int, float], page: A4
) -> list[int]:
    """`break_inside="avoid_row"` を尊重して改ページ位置を決定する。"""
    raise NotImplementedError


def solve(page: A4, table: Table, rows: list[Any]) -> PlacementPlan:
    """制約解決のエントリポイント。PlacementPlan を返す純粋関数。"""
    raise NotImplementedError
