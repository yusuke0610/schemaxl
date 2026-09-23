"""overflow 戦略と、幅への収め方 (`fit`)。

セル内容が割り当て幅に収まらないときの挙動を表す。Wrap / Shrink / Truncate の 3 種類。

## 文字幅計測の注入

行が何行に折り返るか・フォントをどこまで縮めれば収まるかは、文字列の描画幅に依存する。
実フォントのメトリクスに直接依存させるとテストが環境依存になるため、幅計測は
`TextMeasurer = Callable[[text, font_pt], pt]` として **注入** する。
未指定時は東アジア文字幅に基づく近似計測器 `default_measure` を用いる。

`fit` は solver 層とのインターフェースである `FitResult` を返す純粋関数。
副作用は持たない(Warning も返り値に載せるだけで送出しない)。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

# Excel 標準フォント (Calibri) の既定サイズ。base_font_pt の既定値。
DEFAULT_FONT_PT = 11.0

# (text, font_pt) -> 描画幅 pt。実フォント非依存にするための注入点。
TextMeasurer = Callable[[str, float], float]


class OverflowStrategy:
    """overflow 戦略の基底。"""


@dataclass(frozen=True)
class Wrap(OverflowStrategy):
    """テキストを折り返して行高を伸ばす。引数を取らない。"""


@dataclass(frozen=True)
class Shrink(OverflowStrategy):
    """フォントを縮小して収める。min_pt を下限とする。"""

    min_pt: float


@dataclass(frozen=True)
class Truncate(OverflowStrategy):
    """幅に収まる位置で切り詰め、末尾に `marker`(既定 "…")を付す。1 行のまま。

    情報が失われる戦略なので、切り詰めが起きたら solver が必ず警告
    (`LayoutWarning(kind="truncated")`)を積む。切る位置は書記素クラスタ
    (見た目の 1 文字)の境界で、絵文字や結合文字を途中で割らない。
    """

    marker: str = "…"


@dataclass(frozen=True)
class FitResult:
    """`fit` の結果。solver 層はこれを見て行高・フォントを決める。

    - lines:    折り返し後の各行(Shrink や 1 行に収まる場合は要素 1)。
    - font_pt:  確定フォントサイズ(Wrap では base のまま、Shrink では縮小後)。
    - warnings: 収めきれなかった等の警告(仕様決定2)。送出はしない。
    - truncated: Truncate で内容を切り詰めたか(lines は切り詰め後の表示文字列)。
    """

    lines: tuple[str, ...]
    font_pt: float
    warnings: tuple[str, ...] = field(default_factory=tuple)
    truncated: bool = False

    @property
    def line_count(self) -> int:
        return len(self.lines)


# --- 既定の計測器 --------------------------------------------------------


def _em_fraction(ch: str) -> float:
    """1 文字の em 幅の目安。全角 (F/W) は 1.0、半角は 0.5。"""
    return 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5


def default_measure(text: str, font_pt: float) -> float:
    """東アジア文字幅に基づく近似計測器(実フォント非依存)。"""
    return sum(_em_fraction(c) for c in text) * font_pt


# --- 折り返し ------------------------------------------------------------


def _force_break(word: str, width_pt: float, font_pt: float, measure: TextMeasurer) -> list[str]:
    """単語境界のない長大語を、各断片が width 以下になるよう文字単位で割る。

    1 文字だけで width を超える場合でも、その 1 文字を 1 断片として確定させ
    (無限ループを避ける)、文字は落とさない。
    """
    chunks: list[str] = []
    cur = ""
    for ch in word:
        if cur and measure(cur + ch, font_pt) > width_pt:
            chunks.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        chunks.append(cur)
    return chunks


def _wrap_lines(text: str, width_pt: float, font_pt: float, measure: TextMeasurer) -> list[str]:
    """空白区切りの単語を貪欲に詰めて折り返す。単語が幅を超えれば強制分割する。"""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        candidate = word if not cur else f"{cur} {word}"
        if cur and measure(candidate, font_pt) <= width_pt:
            cur = candidate
            continue
        # ここに来たら word は新しい行に置く(現在行があれば確定する)。
        if cur:
            lines.append(cur)
            cur = ""
        if measure(word, font_pt) <= width_pt:
            cur = word
        else:
            broken = _force_break(word, width_pt, font_pt, measure)
            lines.extend(broken[:-1])
            cur = broken[-1] if broken else ""
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit_wrap(text: str, width_pt: float, base_font_pt: float, measure: TextMeasurer) -> FitResult:
    lines = _wrap_lines(text, width_pt, base_font_pt, measure)
    return FitResult(lines=tuple(lines), font_pt=base_font_pt)


def _fit_shrink(
    text: str, width_pt: float, base_font_pt: float, min_pt: float, measure: TextMeasurer
) -> FitResult:
    at_base = measure(text, base_font_pt)
    if at_base <= width_pt or at_base == 0:
        return FitResult(lines=(text,), font_pt=base_font_pt)
    # 描画幅は font_pt に比例する(スケーラブルフォントの前提)。
    needed = base_font_pt * width_pt / at_base
    if needed >= min_pt:
        return FitResult(lines=(text,), font_pt=needed)
    # min_pt でも収まらない → min_pt で確定し、警告を残す(仕様決定2)。
    warning = f"min_pt={min_pt}pt でも幅 {width_pt:.1f}pt に収まらない: {text!r}"
    return FitResult(lines=(text,), font_pt=min_pt, warnings=(warning,))


# --- 切り詰め ------------------------------------------------------------

_ZWJ = "\u200d"


def _is_regional_indicator(ch: str) -> bool:
    return "\U0001f1e6" <= ch <= "\U0001f1ff"


def _extends_cluster(ch: str) -> bool:
    """直前の文字に続けて 1 つの書記素クラスタを成す文字か。

    結合文字(濁点 U+3099 などの Mn / Me / Mc)、ZWJ、異体字セレクタ(IVS を含む)、
    肌色修飾子、タグ文字(地域旗)、ハングルの中声・終声字母。
    """
    code = ord(ch)
    return (
        unicodedata.category(ch) in ("Mn", "Me", "Mc")
        or ch == _ZWJ
        or 0xFE00 <= code <= 0xFE0F  # 異体字セレクタ
        or 0xE0100 <= code <= 0xE01EF  # 異体字セレクタ補助(IVS)
        or 0x1F3FB <= code <= 0x1F3FF  # 肌色修飾子
        or 0xE0020 <= code <= 0xE007F  # タグ文字
        or 0x1160 <= code <= 0x11FF  # ハングル中声・終声字母
    )


def graphemes(text: str) -> list[str]:
    """text を書記素クラスタ(見た目の 1 文字)に分割する。

    Unicode の拡張書記素クラスタ規則のうち、帳票で実際に現れる範囲を実装する:
    CR LF、結合文字・修飾子の後続、ZWJ による絵文字連結、地域指示子(国旗)の 2 文字組。
    外部依存(`regex` モジュール)を持ち込まないための近似。
    """
    clusters: list[str] = []
    for ch in text:
        if clusters:
            last = clusters[-1]
            prev = last[-1]
            if (
                (prev == "\r" and ch == "\n")
                or prev == _ZWJ
                or _extends_cluster(ch)
                or (
                    _is_regional_indicator(ch)
                    and _is_regional_indicator(prev)
                    and sum(_is_regional_indicator(c) for c in last) % 2 == 1
                )
            ):
                clusters[-1] = last + ch
                continue
        clusters.append(ch)
    return clusters


def _fit_truncate(
    text: str, width_pt: float, base_font_pt: float, marker: str, measure: TextMeasurer
) -> FitResult:
    if measure(text, base_font_pt) <= width_pt:
        return FitResult(lines=(text,), font_pt=base_font_pt)
    # 収まる最長の接頭辞を探す。接頭辞 + marker の幅で判定する(marker の幅を差し引く)。
    kept = ""
    for cluster in graphemes(text):
        if measure(kept + cluster + marker, base_font_pt) > width_pt:
            break
        kept += cluster
    shown = kept + marker
    warnings: tuple[str, ...] = ()
    if measure(shown, base_font_pt) > width_pt:
        warnings = (f"省略記号 {marker!r} さえ幅 {width_pt:.1f}pt に収まらない: {text!r}",)
    return FitResult(lines=(shown,), font_pt=base_font_pt, warnings=warnings, truncated=True)


def fit(
    text: str,
    width_pt: float,
    strategy: OverflowStrategy | type[OverflowStrategy],
    *,
    base_font_pt: float = DEFAULT_FONT_PT,
    measure: TextMeasurer = default_measure,
) -> FitResult:
    """`text` を幅 `width_pt` に、`strategy` に従って収める純粋関数。

    Wrap は行を増やし(フォントは base のまま)、Shrink はフォントを縮める
    (行は 1 行のまま、min_pt が下限)、Truncate は切り詰めて marker を付す
    (1 行のまま、`truncated=True`)。幅計測は `measure` で注入する。
    """
    strategy = normalize(strategy)
    if isinstance(strategy, Wrap):
        return _fit_wrap(text, width_pt, base_font_pt, measure)
    if isinstance(strategy, Shrink):
        return _fit_shrink(text, width_pt, base_font_pt, strategy.min_pt, measure)
    if isinstance(strategy, Truncate):
        return _fit_truncate(text, width_pt, base_font_pt, strategy.marker, measure)
    raise TypeError(f"未知の overflow 戦略: {strategy!r}")


def normalize(strategy: OverflowStrategy | type[OverflowStrategy]) -> OverflowStrategy:
    """overflow 戦略の指定を常にインスタンスへ正規化する。

    `overflow=Wrap`(クラス参照)も `overflow=Wrap()`(インスタンス)も受け付ける。
    ただし Shrink のように必須引数を持つ戦略にクラス参照を渡すと、インスタンス化に
    失敗して TypeError になる(`Shrink` は min_pt が必須)。
    """
    if isinstance(strategy, OverflowStrategy):
        return strategy
    if isinstance(strategy, type) and issubclass(strategy, OverflowStrategy):
        return strategy()  # 引数なし戦略のみ成功。Shrink は TypeError。
    raise TypeError(f"overflow 戦略ではない: {strategy!r}")


# --- 将来構想(Roadmap 参照。未提供)---
# class SplitBlock(OverflowStrategy): ...    # 2 ブロックへ展開(Block 階層 #16 の後)
