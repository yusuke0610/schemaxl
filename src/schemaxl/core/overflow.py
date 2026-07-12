"""overflow 戦略。

セル内容が割り当て幅に収まらないときの挙動を表す。
MVP では Wrap / Shrink の 2 種類。将来は Ellipsis / SplitBlock を追加予定。

これらは制約解決 (solver) が参照するマーカー / 設定オブジェクトであり、
自身は副作用を持たない。本ファイルは骨格のため中身は未実装。
"""

from __future__ import annotations

from dataclasses import dataclass


class OverflowStrategy:
    """overflow 戦略の基底。"""


@dataclass(frozen=True)
class Wrap(OverflowStrategy):
    """テキストを折り返して行高を伸ばす。引数を取らない。"""


@dataclass(frozen=True)
class Shrink(OverflowStrategy):
    """フォントを縮小して収める。min_pt を下限とする。"""

    min_pt: float


def normalize(strategy: OverflowStrategy | type[OverflowStrategy]) -> OverflowStrategy:
    """overflow 戦略の指定を常にインスタンスへ正規化する。

    利用側では `overflow=Wrap()`(インスタンス)を推奨するが、引数を取らない
    戦略についてはクラス参照(`overflow=Wrap`)でも受け付け、ここで
    `Wrap()` のようにインスタンス化して統一する。
    """
    raise NotImplementedError


# --- 将来構想(Roadmap 参照。MVP では未提供)---
# class Ellipsis(OverflowStrategy): ...      # 省略記号で切り詰め
# class SplitBlock(OverflowStrategy): ...    # 2 ブロックへ展開
