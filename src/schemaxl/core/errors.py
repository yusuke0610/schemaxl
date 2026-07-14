"""レイアウト制約が解けないときの例外。

solver が「紙に収まらない」構成を検出したときに送出する。超過量や行番号を
構造化フィールドとして持たせ、呼び出し側・テストが数値で検証できるようにする。
将来 `strict=False` で緩和する余地を残すが、MVP では常に送出する。
"""

from __future__ import annotations


class LayoutError(Exception):
    """レイアウトがページに収まらないことを表す。

    - overage_pt: 印字可能領域をどれだけ超過したか(pt)。
    - row:        原因となった行番号(0 始まり。行に紐づく場合のみ)。
    """

    def __init__(
        self,
        message: str,
        *,
        overage_pt: float | None = None,
        row: int | None = None,
    ) -> None:
        super().__init__(message)
        self.overage_pt = overage_pt
        self.row = row
