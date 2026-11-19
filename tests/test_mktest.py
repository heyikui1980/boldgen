"""测试文档（.docx）生成的测试。"""

from __future__ import annotations

import zipfile

import pytest

from boldgen.mktest import DEFAULT_SAMPLE, build_test_docx


@pytest.fixture
def docx(tmp_path):
    path = tmp_path / "test.docx"
    build_test_docx(str(path), [("SimSun", "SimSun"), ("Noto", "Noto Serif CJK SC")])
    return str(path)


def test_creates_valid_zip(docx):
    with zipfile.ZipFile(docx) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
    assert {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
    } <= names


def test_document_contains_bold_and_regular_runs(docx):
    with zipfile.ZipFile(docx) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "<w:b/>" in document
    assert DEFAULT_SAMPLE in document


def test_document_references_each_family(docx):
    with zipfile.ZipFile(docx) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert 'w:eastAsia="SimSun"' in document
    assert 'w:eastAsia="Noto Serif CJK SC"' in document
    assert "[SimSun BOLD]" in document


def test_document_has_two_runs_per_family(docx):
    with zipfile.ZipFile(docx) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert document.count("<w:p>") == 1 + 2 * 2


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "test.docx"
    build_test_docx(str(path), [("A", "A")])
    assert path.exists()


def test_custom_sample(tmp_path):
    path = tmp_path / "t.docx"
    build_test_docx(str(path), [("A", "A")], sample="测试")
    with zipfile.ZipFile(str(path)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "测试" in document
