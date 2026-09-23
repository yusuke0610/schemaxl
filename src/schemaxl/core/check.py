"""レンダリング前の静的検証(`schemaxl check` の本体)。

データを一切見ずに、行モデルの宣言(`Field` のデータ制約 + `Layout` のレイアウト制約)
だけから「紙に収まらない」ことが確定する構成を見つける。

検証ルールを solver とは別に書くことはしない。`max_length` いっぱいまで最も幅の広い
文字で埋めた **最悪ケースの 1 行** を合成し、実物の `solve` に通す。こうすると検証と
実際のレンダリングの判定が構造的に食い違わない(solver が単一の真実)。

結果は実行時と同じ `LayoutWarning` で返す。`is_error` が真のもの(レイアウトが解けない、
意図せず見切れる)は CI を落とすべき問題で、それ以外は確認を促す警告。この線引きは
`render(strict=True)` が止めるもの・止めないものと同じにしてある。

I/O を持たない純粋関数。CLI(`schemaxl.cli`)はこれを呼んで表示するだけ。
"""

from __future__ import annotations

import types
import typing
from dataclasses import replace
from typing import Any, get_args, get_origin

from schemaxl.core.errors import (
    WARNING_LAYOUT_ERROR,
    WARNING_NO_LAYOUT,
    WARNING_OVERFLOW,
    WARNING_UNBOUNDED,
    LayoutError,
    LayoutWarning,
)
from schemaxl.core.model import Column, Report, columns_of
from schemaxl.core.overflow import DEFAULT_FONT_PT, TextMeasurer, default_measure

# 静的検証が CI を落とすべき問題とみなす種別。
ERROR_KINDS = frozenset({WARNING_LAYOUT_ERROR, WARNING_OVERFLOW})

# 最悪ケースの文字の候補。計測器ごとに最も幅の広いものを使う(既定の計測器では全角)。
_WIDE_CHAR_CANDIDATES = ("あ", "漢", "Ｗ", "W", "M", "@", "%")


def is_error(finding: LayoutWarning) -> bool:
    """CI を落とすべき問題か(レイアウトが解けない・意図せず見切れる)。"""
    return finding.kind in ERROR_KINDS


def _widest_char(measure: TextMeasurer) -> str:
    return max(_WIDE_CHAR_CANDIDATES, key=lambda ch: measure(ch, DEFAULT_FONT_PT))


def _strip_optional(annotation: Any) -> Any:
    """`str | None` / `Optional[str]` から None を外す。"""
    if get_origin(annotation) in (typing.Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _field_info(model: type[Any], name: str) -> Any:
    fields: dict[str, Any] = getattr(model, "model_fields", {})
    return fields.get(name)


def _max_length(field_info: Any) -> int | None:
    for constraint in getattr(field_info, "metadata", ()):
        bound = getattr(constraint, "max_length", None)
        if isinstance(bound, int):
            return bound
    return None


def _worst_case_value(
    column: Column, model: type[Any], wide_char: str
) -> tuple[str | None, LayoutWarning | None]:
    """列の最悪ケースの値と、検証できない場合の警告を返す。

    - `str`(Optional 含む)で `max_length` あり → 最も幅の広い文字 × max_length
    - `str` で `max_length` なし / `list` → 上限が無く検証できない(unbounded 警告)
    - それ以外(数値・日付等)→ 対象外(値なしで solver に通す)
    """
    field_info = _field_info(model, column.field_name)
    annotation = _strip_optional(getattr(field_info, "annotation", None))
    if annotation is str:
        bound = _max_length(field_info)
        if bound is not None:
            return wide_char * bound, None
        reason = (
            "max_length が無い str 列は上限が無く、収まるかを静的に検証できない"
            "(Field(max_length=...) を付けると検証できる)"
        )
    elif get_origin(annotation) in (list, tuple):
        reason = "list 列は結合後の長さに上限が無く、収まるかを静的に検証できない"
    else:
        return None, None
    return None, LayoutWarning(
        message=f"{column.field_name}: {reason}",
        kind=WARNING_UNBOUNDED,
        field_name=column.field_name,
        col=column.index + 1,
    )


def _missing_layouts(model: type[Any], columns: list[Column]) -> list[LayoutWarning]:
    fields: dict[str, Any] = getattr(model, "model_fields", {})
    laid_out = {column.field_name for column in columns}
    return [
        LayoutWarning(
            message=f"{name}: Layout が付いていないため列にならない(意図的か確認)",
            kind=WARNING_NO_LAYOUT,
            field_name=name,
        )
        for name in fields
        if name not in laid_out
    ]


def check(report: type[Report[Any]], *, measure: TextMeasurer | None = None) -> list[LayoutWarning]:
    """`report` の宣言だけから、紙に収まらない構成を検出する。

    `measure` は `render` と同じ文字幅計測器(未指定なら `default_measure`)。
    最悪ケースは「max_length いっぱいまで、その計測器で最も幅の広い文字で埋めた行」。
    検出結果は行モデルの宣言順(Layout なし → 列ごとの上限なし → solver の判定)に並ぶ。
    """
    # solver は model に依存するので、循環 import 回避で遅延 import する。
    from schemaxl.core.solver import solve

    measure = measure if measure is not None else default_measure
    model = report._row_model()
    table = report.body if report.body.bind is not None else replace(report.body, bind=model)
    columns = columns_of(model)

    findings = _missing_layouts(model, columns)
    wide_char = _widest_char(measure)
    worst_row: dict[str, Any] = {}
    for column in columns:
        value, unbounded = _worst_case_value(column, model, wide_char)
        if unbounded is not None:
            findings.append(unbounded)
        worst_row[column.field_name] = value

    try:
        plan = solve(report.page, table, [worst_row], measure=measure)
    except LayoutError as error:
        findings.append(
            LayoutWarning(
                message=f"最悪ケースでレイアウトが解けない: {error}",
                kind=WARNING_LAYOUT_ERROR,
                overage_pt=error.overage_pt,
            )
        )
        return findings

    # 最悪ケースの行はデータではないので、行番号は意味を持たない(ヘッダ行は残す)。
    for warning in plan.warnings:
        findings.append(
            replace(
                warning,
                message=f"最悪ケースで: {warning.message}",
                row=warning.row if warning.row == 1 else None,
            )
        )
    return findings
