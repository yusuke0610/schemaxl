"""コマンドラインインターフェース。

    schemaxl check myapp.reports:AllergyReport [--strict] [--format text|json]

検出ロジックは `core.check` の純粋関数にあり、ここは対象の import と表示・終了コード
だけを受け持つ。終了コード:

- 0: 問題なし(warning のみで --strict なしを含む)
- 1: error がある、または --strict で warning がある
- 2: 使い方の誤り(対象を import できない、Report ではない等)
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from schemaxl.core.check import check, is_error
from schemaxl.core.errors import LayoutWarning
from schemaxl.core.model import Report

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


def _load_report(target: str) -> type[Report[Any]]:
    """`module.path:ClassName` 形式の指定から Report サブクラスを取り出す。"""
    module_name, sep, attr_path = target.partition(":")
    if not sep or not module_name or not attr_path:
        raise ValueError(f"対象は 'module.path:ReportClass' の形式で指定する: {target!r}")
    # カレントディレクトリのモジュール(examples.allergy_report 等)も import できるようにする。
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    obj: Any = importlib.import_module(module_name)
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    if not (isinstance(obj, type) and issubclass(obj, Report)):
        raise TypeError(f"{target} は Report のサブクラスではない: {obj!r}")
    return obj


def _severity(finding: LayoutWarning) -> str:
    return "error" if is_error(finding) else "warning"


def _render_text(target: str, findings: list[LayoutWarning]) -> str:
    lines = [target]
    for finding in findings:
        location = "".join(
            part
            for part in (
                f" 列 {finding.col}" if finding.col is not None else "",
                f" 行 {finding.row}" if finding.row is not None else "",
            )
        )
        lines.append(f"  {_severity(finding)} [{finding.kind}]{location}: {finding.message}")
    errors = sum(is_error(finding) for finding in findings)
    lines.append(f"{errors} error(s), {len(findings) - errors} warning(s)")
    return "\n".join(lines)


def _render_json(target: str, findings: list[LayoutWarning]) -> str:
    payload = {
        "target": target,
        "findings": [{"severity": _severity(f), **asdict(f)} for f in findings],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _run_check(args: argparse.Namespace) -> int:
    try:
        report = _load_report(args.target)
    except (ImportError, AttributeError, ValueError, TypeError) as error:
        print(f"schemaxl check: {error}", file=sys.stderr)
        return EXIT_USAGE

    findings = check(report)
    render = _render_json if args.format == "json" else _render_text
    print(render(args.target, findings))

    has_errors = any(is_error(finding) for finding in findings)
    if has_errors or (args.strict and findings):
        return EXIT_FINDINGS
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schemaxl", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    check_parser = commands.add_parser(
        "check", help="レンダリング前に、宣言だけから紙に収まらない構成を検出する"
    )
    check_parser.add_argument("target", help="検証する Report(例: myapp.reports:AllergyReport)")
    check_parser.add_argument(
        "--strict", action="store_true", help="warning も失敗(終了コード 1)として扱う"
    )
    check_parser.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    return _run_check(args)


if __name__ == "__main__":
    sys.exit(main())
