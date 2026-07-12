"""schemaxl — Pydantic モデルを単一の真実として Excel 帳票を宣言的に生成する。

公開 API はこのモジュールから re-export する。詳細な設計は README.md を参照。

現時点では骨格 (skeleton) のみ。各シンボルの実体は未実装。
"""

from schemaxl.core.model import (
    A4,
    Auto,
    Fill,
    Layout,
    Report,
    Table,
)
from schemaxl.core.overflow import Shrink, Wrap
from schemaxl.core.units import mm, pt

__all__ = [
    "Report",
    "Table",
    "Layout",
    "A4",
    "Auto",
    "Fill",
    "Wrap",
    "Shrink",
    "mm",
    "pt",
]

__version__ = "0.1.0.dev0"
