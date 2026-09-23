"""README 掲載の API スケッチをそのまま動かす example。

`python examples/allergy_report.py` を実行すると、カレントディレクトリに
`report.xlsx`(A4 縦・ヘッダ行を各ページで繰り返す帳票)を書き出す。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from schemaxl import A4, Auto, Fill, Layout, Report, Shrink, Table, Wrap, mm


class AllergyRow(BaseModel):
    child_name: Annotated[
        str,
        Field(max_length=30),  # データ制約
        Layout(header="児童名", width=Auto(min=mm(30)), overflow=Wrap()),  # レイアウト制約
    ]
    allergens: Annotated[
        list[str],
        Layout(header="アレルゲン", width=Fill, join="、", overflow=Shrink(min_pt=8)),
    ]


class AllergyReport(Report[AllergyRow]):
    page = A4(orientation="portrait", margin=mm(15))
    # 行モデルはジェネリクスから推論されるため bind は省略。
    body = Table(break_inside="avoid_row", repeat_header=True)


def main() -> None:
    # render は dict のリスト(キー → フィールド名)を受け付ける。
    # タプルのリスト(フィールド宣言順の位置マップ)でも可。
    rows = [
        {"child_name": "山田 太郎", "allergens": ["卵", "乳"]},
        {"child_name": "佐藤 花子", "allergens": ["小麦", "そば", "落花生"]},
    ]
    AllergyReport.render(rows, "report.xlsx")


if __name__ == "__main__":
    main()
