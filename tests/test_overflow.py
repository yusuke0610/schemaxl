"""overflow 戦略のテスト置き場(骨格)。

Wrap(折り返しによる行高増加)と Shrink(min_pt を下限とするフォント縮小)の
振る舞いをここでテストする想定。
"""

import pytest


@pytest.mark.skip(reason="骨格 (skeleton) — overflow 未実装")
def test_wrap_increases_row_height() -> None:
    ...


@pytest.mark.skip(reason="骨格 (skeleton) — overflow 未実装")
def test_shrink_respects_min_pt() -> None:
    ...
