"""TTC（TrueType Collection）源字体的处理。

背景：宋体的 Regular 与 NSimSun 装在同一个 ``simsun.ttc`` 里，分别是
face 0 和 face 1。生成的产物是**单 face** 的 .ttf，所以"被检查的 face 序号"
与"源字体的 face 序号"必须分开传——以前混用了，导致 TTC 的 face 1 一律
自检失败。
"""

from __future__ import annotations

import pytest

from boldgen.builder import build_bold
from boldgen.sfnt import Font
from boldgen.verify import ink_ratio, verify_font

from conftest import make_font_bytes, make_ttc_bytes, SQUARE, DONUT


def test_font_reads_ttc_faces(ttc_font):
    font = Font(open(ttc_font, "rb").read(), 0)
    assert font.is_collection
    assert font.num_fonts == 2


def test_build_bold_from_ttc_face_1(tmp_path, ttc_font):
    """从 TTC 的第 2 个 face 生成粗体。"""
    out = tmp_path / "Donut-Bold.ttf"
    result = build_bold(ttc_font, str(out), face_index=1)
    assert result.family == "DonutFam"
    assert out.exists()


def test_verify_font_accepts_ttc_face_1(tmp_path, ttc_font):
    """自检时产物是 face 0、源是 face 1——必须能通过。"""
    out = tmp_path / "Donut-Bold.ttf"
    build_bold(ttc_font, str(out), face_index=1)
    result = verify_font(str(out), 0, source_path=ttc_font, source_face_index=1)
    assert result.ok, result.errors
    assert result.errors == []
    assert result.info["ink_ratio"] > 1.0


def test_verify_font_rejects_face_index_on_single_face_file(tmp_path, ttc_font):
    """把 face 序号错传给单 face 文件时，必须报错而不是静默通过。"""
    out = tmp_path / "Donut-Bold.ttf"
    build_bold(ttc_font, str(out), face_index=1)
    result = verify_font(str(out), 1)
    assert not result.ok
    assert any("sfnt" in message for message in result.errors)


def test_ink_ratio_with_different_face_indices(tmp_path, ttc_font):
    """墨量比的两个 face 序号可以不同。"""
    out = tmp_path / "Donut-Bold.ttf"
    build_bold(ttc_font, str(out), face_index=1)
    ratio = ink_ratio(str(out), ttc_font, 0, 1)
    assert ratio is not None
    assert ratio > 1.0


def test_build_bold_from_ttc_face_0(tmp_path, ttc_font):
    out = tmp_path / "Square-Bold.ttf"
    result = build_bold(ttc_font, str(out), face_index=0)
    assert result.family == "SquareFam"


def test_ttc_with_single_face(tmp_path):
    path = tmp_path / "One.ttc"
    path.write_bytes(make_ttc_bytes([make_font_bytes([SQUARE], family="SoloFam")]))
    out = tmp_path / "Solo-Bold.ttf"
    result = build_bold(str(path), str(out), face_index=0)
    assert result.family == "SoloFam"


def test_ttc_face_index_out_of_range(tmp_path):
    path = tmp_path / "One.ttc"
    path.write_bytes(make_ttc_bytes([make_font_bytes([SQUARE])]))
    with pytest.raises(ValueError):
        build_bold(str(path), str(tmp_path / "x.ttf"), face_index=3)
