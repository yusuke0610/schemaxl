"""openpyxl バックエンド。

PlacementPlan を受け取り、openpyxl で .xlsx を書き出す。
ここが唯一の副作用境界であり、レイアウト判断は一切行わない
(すべて solver が決定済みの前提)。

本ファイルは骨格のため書き出しロジックは未実装。
"""

from __future__ import annotations

from schemaxl.core.plan import PlacementPlan


def write_xlsx(plan: PlacementPlan, path: str) -> None:
    """PlacementPlan を path の .xlsx として書き出す。

    - column_widths / row_heights を反映
    - CellPlacement を書き込み(結合セル・フォント pt・折り返しを適用)
    - page_breaks / 印刷設定(A4・余白・ヘッダ繰り返し)を反映
    """
    raise NotImplementedError
