"""セル値の型と表示文字列。

モデルが `int` / `Decimal` / `date` と知っている値を、出力の一歩手前で `str()` して
捨てないための層。solver が 1 セルぶんの値を `CellValue` に変換し、

- plan に載せる値(`value` / `kind` / `number_format`)
- 幅計測に使う表示文字列(`display`)

を **同じ 1 か所で** 決める。計測と書き込みで見た目が食い違うと見切れるため、
「値 → 表示文字列」の変換はここ以外に持たない。

plan は `dataclasses.asdict` + `json.dumps` が通る純データに保つので、JSON が
そのまま表せない `Decimal` / `date` / `datetime` は文字列(ISO 8601)に符号化し、
`kind` で元の型を示す。元の型へ戻すのは backend の仕事(符号化の解読であって
レイアウト判断ではない)。

`number_format` は Excel の書式文字列のうち、表示文字列を確実に再現できるものだけを
受け付ける。再現できない書式を通すと幅の見積もりがずれ、見切れを保証できない。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

# plan に載せる値の型。いずれも JSON がそのまま表せる。
PlanValue = str | int | float | bool | None

# plan 上の値の種別。backend はこれを見て元の型へ戻す。
ValueKind = Literal["text", "number", "decimal", "bool", "date", "datetime"]

# 数値書式: "0" / "0.00" / "#,##0" / "#,##0.00" / "0%" / "0.0%"。
_NUMBER_FORMAT = re.compile(r"(?P<int>#,##0|0)(?:\.(?P<dec>0+))?(?P<pct>%?)")

# 日付・時刻書式 → 表示文字列を作る関数。Excel の m / mm は文脈で「月」にも「分」にも
# なるため、汎用の解釈器は持たず、表示を確実に再現できる書式だけを列挙する。
_DATE_FORMATS: dict[str, Callable[[datetime], str]] = {
    "yyyy-mm-dd": lambda d: f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
    "yyyy/mm/dd": lambda d: f"{d.year:04d}/{d.month:02d}/{d.day:02d}",
    "yyyy/m/d": lambda d: f"{d.year:04d}/{d.month}/{d.day}",
    "hh:mm": lambda d: f"{d.hour:02d}:{d.minute:02d}",
    "hh:mm:ss": lambda d: f"{d.hour:02d}:{d.minute:02d}:{d.second:02d}",
    "yyyy-mm-dd hh:mm": lambda d: f"{d:%Y-%m-%d %H:%M}",
    "yyyy-mm-dd hh:mm:ss": lambda d: f"{d:%Y-%m-%d %H:%M:%S}",
    "yyyy/mm/dd hh:mm": lambda d: f"{d:%Y/%m/%d %H:%M}",
    "yyyy/mm/dd hh:mm:ss": lambda d: f"{d:%Y/%m/%d %H:%M:%S}",
}

# 書式未指定の日付・日時に solver が与える既定の書式。backend の既定に任せない。
DEFAULT_DATE_FORMAT = "yyyy-mm-dd"
DEFAULT_DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"

# 書式未指定の float の表示桁。Excel の「標準」表示は有効桁が約 11 桁。
# これより長く見積もる分には列が広くなるだけで見切れない(安全側)。
_GENERAL_FLOAT_DIGITS = 11


@dataclass(frozen=True)
class CellValue:
    """1 セルぶんの値。plan に載せる値と、幅計測に使う表示文字列の組。"""

    value: PlanValue
    kind: ValueKind
    number_format: str | None
    display: str

    @property
    def wrappable(self) -> bool:
        """Excel が折り返せる値か。数値・日付は折り返されず「###」になる。"""
        return self.kind == "text"


def check_number_format(number_format: str) -> None:
    """対応していない書式を ValueError にする(`Layout` の宣言時に呼ぶ)。"""
    if _is_number_format(number_format) or number_format in _DATE_FORMATS:
        return
    supported = ", ".join(["0", "0.00", "#,##0", "#,##0.00", "0%", "0.0%", *_DATE_FORMATS])
    raise ValueError(
        f"未対応の number_format: {number_format!r}"
        f"(表示幅を再現できる書式のみ受け付ける: {supported})"
    )


def _is_number_format(number_format: str) -> bool:
    return _NUMBER_FORMAT.fullmatch(number_format) is not None


def _format_number(value: float | Decimal, number_format: str) -> str:
    match = _NUMBER_FORMAT.fullmatch(number_format)
    assert match is not None  # check_number_format 済み
    decimals = len(match["dec"] or "")
    grouping = "," if match["int"] == "#,##0" else ""
    percent = match["pct"] == "%"
    number = Decimal(value) if not isinstance(value, float) else value
    if percent:
        number = number * 100
    return f"{number:{grouping}.{decimals}f}" + ("%" if percent else "")


def _general_number(value: float | Decimal) -> str:
    if isinstance(value, float):
        return format(value, f".{_GENERAL_FLOAT_DIGITS}g")
    return str(value)


def _check_kind(field_name: str, number_format: str, *, date_like: bool) -> None:
    """値の種別と書式の種別(数値 / 日付)が噛み合わない宣言を ValueError にする。"""
    if date_like and number_format not in _DATE_FORMATS:
        raise ValueError(f"{field_name}: 日付・時刻の値に数値書式 {number_format!r} は使えない")
    if not date_like and number_format in _DATE_FORMATS:
        raise ValueError(f"{field_name}: 数値の値に日付書式 {number_format!r} は使えない")


def to_cell_value(
    raw: Any, *, join: str, number_format: str | None, field_name: str = "?"
) -> CellValue:
    """モデルのフィールド値を `CellValue` へ変換する純粋関数。

    - None → 空セル
    - bool → Excel の論理値(表示 TRUE / FALSE)。int より先に判定する(bool は int の派生)
    - int / float → 数値、Decimal → 文字列に符号化した数値
    - datetime / date → ISO 8601 に符号化した日時・日付。書式未指定なら既定の書式を付ける。
      タイムゾーン付きの datetime は Excel が表せないので ValueError
    - list / tuple → `join` で結合した文字列
    - それ以外 → `str()` した文字列
    """
    if raw is None:
        return CellValue(None, "text", None, "")
    if isinstance(raw, bool):
        return CellValue(raw, "bool", None, "TRUE" if raw else "FALSE")
    if isinstance(raw, (int, float, Decimal)):
        if number_format is not None:
            _check_kind(field_name, number_format, date_like=False)
            display = _format_number(raw, number_format)
        else:
            display = _general_number(raw)
        if isinstance(raw, Decimal):
            return CellValue(str(raw), "decimal", number_format, display)
        return CellValue(raw, "number", number_format, display)
    if isinstance(raw, datetime):
        if raw.tzinfo is not None:
            raise ValueError(
                f"{field_name}: タイムゾーン付きの datetime は Excel に書けない: {raw!r}"
                "(naive な datetime へ変換して渡す)"
            )
        fmt = number_format if number_format is not None else DEFAULT_DATETIME_FORMAT
        _check_kind(field_name, fmt, date_like=True)
        return CellValue(raw.isoformat(), "datetime", fmt, _DATE_FORMATS[fmt](raw))
    if isinstance(raw, date):
        fmt = number_format if number_format is not None else DEFAULT_DATE_FORMAT
        _check_kind(field_name, fmt, date_like=True)
        # Excel の日時はタイムゾーンを持たないので naive のまま(時刻は 0:00)。
        as_datetime = datetime.combine(raw, time())
        return CellValue(raw.isoformat(), "date", fmt, _DATE_FORMATS[fmt](as_datetime))
    if isinstance(raw, (list, tuple)):
        text = join.join(str(item) for item in raw)
        return CellValue(text, "text", None, text)
    text = str(raw)
    return CellValue(text, "text", None, text)
