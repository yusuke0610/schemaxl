"""制約解決層のテスト置き場(骨格)。

solver は純粋関数なのでファイル I/O なしで検証できる。
列幅・行高・改ページの各解決を、極端ケース(max_length ぴったり等)を
含めてここでテストする想定。
"""

import pytest


@pytest.mark.skip(reason="骨格 (skeleton) — solver 未実装")
def test_resolve_column_widths() -> None:
    ...


@pytest.mark.skip(reason="骨格 (skeleton) — solver 未実装")
def test_resolve_page_breaks_avoid_row() -> None:
    ...
