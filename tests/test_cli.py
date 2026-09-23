"""CLI(`schemaxl check`)のテスト。終了コードと出力だけを見る。

検出ロジックの網羅は test_check.py が担う。ここでは対象の import・表示形式・
終了コード(0 / 1 / 2)の配線を確かめる。
"""

import json
import textwrap
import uuid

import pytest

from schemaxl.cli import main

REPORTS = textwrap.dedent(
    """
    from typing import Annotated
    from pydantic import BaseModel, Field
    from schemaxl import A4, Auto, Layout, Report, Shrink, Table, Wrap, mm

    class OkRow(BaseModel):
        name: Annotated[str, Field(max_length=5), Layout(header="名", width=Auto(), overflow=Wrap())]

    class Ok(Report[OkRow]):
        page = A4(margin=mm(15))
        body = Table()

    class WarnRow(BaseModel):
        name: Annotated[str, Layout(header="名", width=Auto(), overflow=Wrap())]

    class WarnOnly(Report[WarnRow]):
        page = A4(margin=mm(15))
        body = Table()

    class TightRow(BaseModel):
        name: Annotated[
            str,
            Field(max_length=30),
            Layout(header="名", width=Auto(max=mm(20)), overflow=Shrink(min_pt=8)),
        ]

    class Tight(Report[TightRow]):
        page = A4(margin=mm(15))
        body = Table()

    NOT_A_REPORT = 1
    """
)


@pytest.fixture
def module(tmp_path, monkeypatch) -> str:
    """一時ディレクトリに帳票定義モジュールを置き、カレントにしてモジュール名を返す。"""
    name = f"reports_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(REPORTS, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def test_clean_report_exits_zero(module, capsys) -> None:
    assert main(["check", f"{module}:Ok"]) == 0
    assert "0 error(s), 0 warning(s)" in capsys.readouterr().out


def test_errors_exit_one_and_are_listed(module, capsys) -> None:
    assert main(["check", f"{module}:Tight"]) == 1
    out = capsys.readouterr().out
    assert "error [overflow] 列 1" in out
    assert "1 error(s), 0 warning(s)" in out


def test_warnings_pass_unless_strict(module, capsys) -> None:
    assert main(["check", f"{module}:WarnOnly"]) == 0
    assert "warning [unbounded]" in capsys.readouterr().out
    assert main(["check", "--strict", f"{module}:WarnOnly"]) == 1


def test_json_output(module, capsys) -> None:
    assert main(["check", "--format", "json", f"{module}:Tight"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == f"{module}:Tight"
    [finding] = payload["findings"]
    assert (finding["severity"], finding["kind"], finding["field_name"]) == (
        "error",
        "overflow",
        "name",
    )


@pytest.mark.parametrize(
    "target",
    ["no_colon_here", "missing_module_xyz:Report", "{module}:Nope", "{module}:NOT_A_REPORT"],
)
def test_bad_targets_exit_two(module, capsys, target: str) -> None:
    assert main(["check", target.format(module=module)]) == 2
    assert "schemaxl check:" in capsys.readouterr().err


def test_command_is_required() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
