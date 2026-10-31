# -*- coding: utf-8 -*-
"""守卫：前端不得再读取 Task.config 的旧 Sheet 引用形态。

统一形态是 ``sheets: [SheetRef]``（多品为 ``products[].sheet``）；C3 平铺键、
单品嵌套 ``sheet{}`` 已由 scripts/migrate_task_config_schema.py 一次性迁移，
读取端不再容忍/回退。
"""

import re
from pathlib import Path

import pytest

JS_ROOTS = (Path("static/js/pages"), Path("static/js/common"))

# 覆盖 config / restartConfig / taskConfig 等所有 *Config 变量；canonical 的
# sheet.spreadsheet_id、products[].sheet、构造中的 sheetConfig.* 不在匹配范围内
LEGACY_PATTERNS = {
    "*.spreadsheet_id": re.compile(r"\b(?!sheetConfig\b)\w*[cC]onfig\.spreadsheet_id\b"),
    "*.sheet_name": re.compile(r"\b(?!sheetConfig\b)\w*[cC]onfig\.sheet_name\b"),
    "*.spreadsheet_title": re.compile(r"\b(?!sheetConfig\b)\w*[cC]onfig\.spreadsheet_title\b"),
    "*.sheet": re.compile(r"\b(?!sheetConfig\b)\w*[cC]onfig\.sheet\b(?!s)"),
    "*.exclude_years": re.compile(r"\b(?!sheetConfig\b)\w*[cC]onfig\.exclude_years\b"),
}


def _js_files():
    for root in JS_ROOTS:
        yield from root.rglob("*.js")


@pytest.mark.parametrize("pattern_name", sorted(LEGACY_PATTERNS))
def test_frontend_has_no_legacy_config_reads(pattern_name):
    pattern = LEGACY_PATTERNS[pattern_name]
    offenders = [
        f"{path}:{line_no}"
        for path in _js_files()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
