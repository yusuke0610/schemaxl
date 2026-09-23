"""バックエンドの共通インターフェース。

バックエンドは `PlacementPlan` を受け取り、物理ファイルへ機械的に写すだけの
副作用の境界。レイアウト判断(幅・高さ・改ページ・シート名)はすべて solver が
plan に載せ済みという前提に立つ。ここは出力ライブラリに依存しない(openpyxl を
import しない)ので、将来の LibreOffice / PDF バックエンドも同じ型で差し込める。
"""

from __future__ import annotations

import os
from typing import Protocol

from schemaxl.core.plan import PlacementPlan

# 書き出し先のパス。str と os.PathLike(pathlib.Path 等)の両方を受け付ける。
StrPath = str | os.PathLike[str]


class Backend(Protocol):
    """`PlacementPlan` を `path` へ書き出すバックエンド。"""

    def write(self, plan: PlacementPlan, path: StrPath) -> None: ...
