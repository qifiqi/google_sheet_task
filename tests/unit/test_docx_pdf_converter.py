"""DOCX → PDF 转换封装测试。

真实转换依赖本机安装 LibreOffice（soffice），缺失时整文件跳过；
soffice 路径在用例内 monkeypatch 注入，不触碰系统配置缓存。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from docx import Document

from app.exceptions import ServiceError
from app.services import docx_pdf_converter


def _detect_soffice() -> str | None:
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in docx_pdf_converter._WINDOWS_SOFFICE_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    return None


@pytest.fixture
def soffice(monkeypatch) -> str:
    path = _detect_soffice()
    if not path:
        pytest.skip("本机未安装 LibreOffice（soffice）")
    monkeypatch.setattr(docx_pdf_converter, "resolve_soffice_path", lambda: path)
    return path


def _minimal_docx_bytes() -> bytes:
    """构造最小合法 DOCX（python-docx 空文档 + 一段文字）。"""
    from io import BytesIO

    document = Document()
    document.add_heading("转换测试", level=1)
    document.add_paragraph("DOCX 转 PDF 单元测试内容。")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_convert_docx_to_pdf_returns_pdf_bytes(soffice):
    buffer, file_size = docx_pdf_converter.convert_docx_to_pdf(_minimal_docx_bytes())
    raw = buffer.getvalue()
    assert file_size == len(raw)
    assert raw[:5] == b"%PDF-"
    assert raw.rstrip().endswith(b"%%EOF")


def test_resolve_soffice_path_missing_raises(monkeypatch):
    monkeypatch.setattr(docx_pdf_converter.shutil, "which", lambda name: None)
    monkeypatch.setattr(docx_pdf_converter, "_WINDOWS_SOFFICE_CANDIDATES", ())
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    with pytest.raises(ServiceError):
        docx_pdf_converter.resolve_soffice_path()
