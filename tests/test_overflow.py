"""overflow 戦略のテスト(第2段)。

ページも表も登場させない。「与えられた幅に文字列を収める」ことだけをテストする。
純 Python で完結する(openpyxl / ファイル I/O 非依存)。

## 文字幅計測の注入

実フォントのメトリクスに依存するとテストが環境依存になる。そこで幅計測は
`measure(text, font_pt) -> pt` という Callable として注入する。ここでは
「1 文字 = font_pt(等幅)」という決定的な計測器を使い、期待値を明快にする。
"""

import pytest

from schemaxl.core.overflow import (
    FitResult,
    Shrink,
    Truncate,
    Wrap,
    fit,
    graphemes,
    normalize,
)


def char_count_measure(text: str, font_pt: float) -> float:
    """1 文字あたり font_pt の等幅計測器(テスト用の決定的メトリクス)。"""
    return len(text) * font_pt


# --- Wrap: 折り返して行を増やす。フォントは変えない ----------------------


def test_wrap_keeps_short_text_on_one_line() -> None:
    r = fit("abc", width_pt=100, strategy=Wrap(), base_font_pt=10, measure=char_count_measure)
    assert r.lines == ("abc",)
    assert r.line_count == 1
    assert r.font_pt == 10
    assert r.warnings == ()


def test_wrap_splits_fullwidth_text_into_two_lines() -> None:
    # 5 文字 × 10pt = 50pt。幅 30pt には 3 文字ぶんまで。
    r = fit("あいうえお", width_pt=30, strategy=Wrap(), base_font_pt=10, measure=char_count_measure)
    assert r.lines == ("あいう", "えお")
    assert r.line_count == 2
    assert r.font_pt == 10  # Wrap はフォントを縮めない


def test_wrap_breaks_at_word_boundary_when_spaces_exist() -> None:
    # "foo bar baz"。幅 7 文字ぶん。単語境界で折り返す(単語を割らない)。
    r = fit("foo bar baz", width_pt=7, strategy=Wrap(), base_font_pt=1, measure=char_count_measure)
    assert r.lines == ("foo bar", "baz")


def test_wrap_force_breaks_a_single_word_longer_than_width() -> None:
    # 空白のない長大語は現実に存在する(URL・化合物名・DNA 配列等)。
    # 単語境界がないので文字単位で強制分割する。
    r = fit("abcdefghij", width_pt=4, strategy=Wrap(), base_font_pt=1, measure=char_count_measure)
    assert r.lines == ("abcd", "efgh", "ij")
    assert "".join(r.lines) == "abcdefghij"  # 文字は失われない


def test_wrap_is_stable_even_when_one_char_exceeds_width() -> None:
    # 1 文字が幅を超えても無限ループせず、1 文字 1 行で確定する。
    r = fit("あい", width_pt=5, strategy=Wrap(), base_font_pt=10, measure=char_count_measure)
    assert r.lines == ("あ", "い")


# --- Shrink: フォントを縮めて 1 行に収める。min_pt が下限 -----------------


def test_shrink_keeps_base_font_when_text_already_fits() -> None:
    r = fit(
        "abc",
        width_pt=100,
        strategy=Shrink(min_pt=6),
        base_font_pt=10,
        measure=char_count_measure,
    )
    assert r.font_pt == 10
    assert r.lines == ("abc",)
    assert r.warnings == ()


def test_shrink_reduces_font_until_text_fits() -> None:
    # 10 文字 × 10pt = 100pt を幅 50pt へ。線形スケールで font=5pt。
    r = fit(
        "abcdefghij",
        width_pt=50,
        strategy=Shrink(min_pt=3),
        base_font_pt=10,
        measure=char_count_measure,
    )
    assert r.font_pt == pytest.approx(5.0)
    assert r.line_count == 1  # Shrink は行を増やさない
    assert r.warnings == ()


def test_shrink_respects_min_pt_and_does_not_go_below_it() -> None:
    # 本来 font=5pt が必要だが min_pt=8 が下限。8pt で確定する。
    r = fit(
        "abcdefghij",
        width_pt=50,
        strategy=Shrink(min_pt=8),
        base_font_pt=10,
        measure=char_count_measure,
    )
    assert r.font_pt == 8.0


def test_shrink_records_warning_when_text_overflows_at_min_pt() -> None:
    # 仕様決定2: min_pt でも収まらないときは Warning を記録して続行する。
    r = fit(
        "abcdefghij",
        width_pt=50,
        strategy=Shrink(min_pt=8),
        base_font_pt=10,
        measure=char_count_measure,
    )
    assert r.warnings != ()
    assert any("収まら" in w for w in r.warnings)


# --- FitResult: solver 層とのインターフェース ----------------------------


def test_fit_result_is_frozen() -> None:
    r = fit("abc", width_pt=100, strategy=Wrap(), base_font_pt=10, measure=char_count_measure)
    assert isinstance(r, FitResult)
    with pytest.raises(AttributeError):
        r.font_pt = 99  # type: ignore[misc]


# --- 既定計測器(注入しない場合)-----------------------------------------


def test_default_measure_treats_fullwidth_as_wider_than_halfwidth() -> None:
    from schemaxl.core.overflow import default_measure

    # 全角は半角より広い。等幅英字 2 文字より全角 1 文字が広い、という直観。
    assert default_measure("あ", 10) > default_measure("a", 10)
    assert default_measure("ab", 10) == pytest.approx(default_measure("あ", 10))


# --- normalize: クラス参照とインスタンスの正規化 -------------------------


def test_normalize_treats_class_reference_and_instance_equally() -> None:
    assert normalize(Wrap) == normalize(Wrap())
    assert normalize(Wrap) == Wrap()


def test_normalize_returns_instance_unchanged() -> None:
    s = Shrink(min_pt=8)
    assert normalize(s) == s


def test_normalize_rejects_class_reference_of_strategy_needing_args() -> None:
    # Shrink は min_pt が必須。クラス参照を渡したら TypeError 相当。
    with pytest.raises(TypeError):
        normalize(Shrink)


def test_normalize_rejects_non_strategy() -> None:
    with pytest.raises(TypeError):
        normalize("wrap")  # type: ignore[arg-type]


# --- Truncate: 切り詰めて省略記号を付す。1 行のまま ------------------------


def test_truncate_leaves_text_that_fits_untouched() -> None:
    result = fit("あいう", 33.0, Truncate(), base_font_pt=11.0, measure=char_count_measure)
    assert result.lines == ("あいう",)
    assert result.truncated is False
    assert result.warnings == ()


def test_truncate_reserves_room_for_the_marker() -> None:
    # 幅 5 文字ぶん。"…" の 1 文字を差し引いて 4 文字残す。
    result = fit("あいうえおかき", 55.0, Truncate(), base_font_pt=11.0, measure=char_count_measure)
    assert result.lines == ("あいうえ…",)
    assert result.truncated is True
    assert result.font_pt == 11.0
    assert result.warnings == ()


def test_truncate_uses_a_custom_marker() -> None:
    result = fit("abcdefgh", 44.0, Truncate(marker="..."), measure=char_count_measure)
    assert result.lines == ("a...",)


def test_truncate_warns_when_even_the_marker_does_not_fit() -> None:
    result = fit("abcdefgh", 20.0, Truncate(marker="..."), measure=char_count_measure)
    assert result.lines == ("...",)
    assert result.truncated is True
    assert len(result.warnings) == 1


def test_truncate_class_reference_is_normalized() -> None:
    assert normalize(Truncate) == Truncate(marker="…")


# --- 書記素クラスタ(切る位置で文字を割らない) -----------------------------


def cluster_measure(text: str, font_pt: float) -> float:
    """見た目の 1 文字 = font_pt の計測器。書記素クラスタ単位の切り詰めを検証する。"""
    return len(graphemes(text)) * font_pt


@pytest.mark.parametrize(
    ("text", "clusters"),
    [
        ("abc", ["a", "b", "c"]),
        ("か\u3099き", ["か\u3099", "き"]),  # 結合文字の濁点
        ("e\u0301x", ["e\u0301", "x"]),  # 結合アクセント
        ("葛\U000e0100飾", ["葛\U000e0100", "飾"]),  # IVS(異体字セレクタ)
        ("\u2764\ufe0fx", ["\u2764\ufe0f", "x"]),  # 絵文字表示の異体字セレクタ
        ("👍🏽x", ["👍🏽", "x"]),  # 肌色修飾子
        ("👨\u200d👩\u200d👧x", ["👨\u200d👩\u200d👧", "x"]),  # ZWJ 連結(家族)
        ("🇯🇵🇺🇸🇫", ["🇯🇵", "🇺🇸", "🇫"]),  # 地域指示子は 2 文字ずつ
        ("a\r\nb", ["a", "\r\n", "b"]),
        ("", []),
    ],
)
def test_graphemes_keep_visual_characters_together(text: str, clusters: list[str]) -> None:
    assert graphemes(text) == clusters


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("👨\u200d👩\u200d👧👨\u200d👩\u200d👧👨\u200d👩\u200d👧", "👨\u200d👩\u200d👧…"),
        ("🇯🇵🇺🇸🇫🇷", "🇯🇵…"),
        ("か\u3099き\u3099く\u3099", "か\u3099…"),
        ("👍🏽👍🏽👍🏽", "👍🏽…"),
    ],
)
def test_truncate_never_splits_a_grapheme_cluster(text: str, shown: str) -> None:
    # 幅は見た目 2 文字ぶん(1 文字 + 省略記号)。
    result = fit(text, 22.0, Truncate(), base_font_pt=11.0, measure=cluster_measure)
    assert result.lines == (shown,)
