"""レイアウトの診断(例外と警告)。

solver が「紙に収まらない」構成を検出したときの表現を集める。超過量や行番号を
構造化フィールドとして持たせ、呼び出し側・テストが数値で検証できるようにする。

- `LayoutError`:   そもそも解けない構成。送出する。
- `LayoutWarning`: 解けはしたが見切れる等の問題。**純データで、送出はしない。**
  solver は `PlacementPlan.warnings` に積むだけで、それをどう扱うか
  (`LayoutError` へ昇格させるか `warnings.warn` するか)は `Report.render` の
  `strict` が決める。静的検証(`schemaxl check`)も同じ構造体を使う想定。
- `SchemaxlWarning`: `warnings.warn` で送出するときのカテゴリ。
"""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class LayoutWarning:
    """レイアウト上の警告。送出しない純データ。

    `PlacementPlan` に載せて直列化されるため、標準型だけで構成する。

    - kind:       警告の種別("overflow" など)。機械的な分岐に使う。
    - field_name: 原因となったモデルのフィールド名。
    - row / col:  シート座標(1 始まり)。位置が特定できる場合のみ。
    - overage_pt: 割り当て幅をどれだけ超過したか(pt)。
    """

    message: str
    kind: str
    field_name: str | None = None
    row: int | None = None
    col: int | None = None
    overage_pt: float | None = None


class SchemaxlWarning(UserWarning):
    """`warnings.warn` で送出するときのカテゴリ。

    利用側が `warnings.filterwarnings` で schemaxl の警告だけを選別できるように
    独自カテゴリにしてある。
    """
