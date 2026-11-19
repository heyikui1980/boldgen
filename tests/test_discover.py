"""字体扫描与家族分组的测试。"""

from __future__ import annotations

import pytest

from boldgen.discover import (
    BOLD_WEIGHT_THRESHOLD,
    REGULAR_WEIGHT,
    Face,
    FamilyInfo,
    _parse_line,
)


def _line(path="/usr/share/fonts/x.ttf", index=0, family="SimSun", style="Regular",
          weight=80, slant=0, fullname="SimSun Regular", ps="SimSun"):
    return (
        f"{path}\t{index}\t{family}\t{style}\t{weight}\t{slant}\t{fullname}\t{ps}"
    )


def test_parse_line_basic():
    face = _parse_line(_line())
    assert face is not None
    assert face.path == "/usr/share/fonts/x.ttf"
    assert face.index == 0
    assert face.family == "SimSun"
    assert face.style == "Regular"
    assert face.weight == 80
    assert face.slant == 0
    assert face.fullname == "SimSun Regular"
    assert face.postscript_name == "SimSun"


def test_parse_line_multi_value_family():
    line = _line(family="SimSun,宋体", style="Regular,常规")
    face = _parse_line(line)
    assert face.families == ["SimSun", "宋体"]
    assert face.family == "SimSun"
    assert face.styles == ["Regular", "常规"]
    assert face.style == "Regular"


def test_parse_line_rejects_garbage():
    assert _parse_line("not a fc-list line") is None
    assert _parse_line("a\tb\tc") is None
    assert _parse_line(_line(weight="x")) is None


def test_bold_threshold_uses_fontconfig_scale():
    """fontconfig 的字重是缩放刻度（Bold=200），不是 CSS 的 700。"""
    assert Face("", 0, "f", ["f"], "Regular", ["Regular"], 80, 0).is_bold is False
    assert Face("", 0, "f", ["f"], "Bold", ["Bold"], 200, 0).is_bold is True
    assert Face("", 0, "f", ["f"], "Black", ["Black"], 210, 0).is_bold is True
    assert Face("", 0, "f", ["f"], "SemiBold", ["SemiBold"], 180, 0).is_bold is False
    assert BOLD_WEIGHT_THRESHOLD == 200
    assert REGULAR_WEIGHT == 80


def test_family_has_real_bold():
    regular = Face("", 0, "f", ["f"], "Regular", ["Regular"], 80, 0)
    bold = Face("", 1, "f", ["f"], "Bold", ["Bold"], 200, 0)
    italic_bold = Face("", 2, "f", ["f"], "Bold Italic", ["Bold Italic"], 200, 20)

    only_regular = FamilyInfo("f", ["f"], [regular])
    assert not only_regular.has_real_bold

    with_bold = FamilyInfo("f", ["f"], [regular, bold])
    assert with_bold.has_real_bold

    only_italic_bold = FamilyInfo("f", ["f"], [italic_bold])
    assert not only_italic_bold.has_real_bold
    assert only_italic_bold.has_bold_any_slant


def test_source_face_prefers_upright_regular():
    italic = Face("/a.ttf", 0, "f", ["f"], "Italic", ["Italic"], 80, 20)
    regular = Face("/b.ttf", 1, "f", ["f"], "Regular", ["Regular"], 80, 0)
    light = Face("/c.ttf", 2, "f", ["f"], "Light", ["Light"], 50, 0)
    family = FamilyInfo("f", ["f"], [italic, light, regular])
    assert family.source_face.path == "/b.ttf"


def test_source_face_falls_back_to_lowest_weight():
    light = Face("/c.ttf", 2, "f", ["f"], "Light", ["Light"], 50, 0)
    medium = Face("/d.ttf", 3, "f", ["f"], "Medium", ["Medium"], 100, 0)
    family = FamilyInfo("f", ["f"], [medium, light])
    assert family.source_face.path == "/c.ttf"


def test_source_face_prefers_lowest_index():
    first = Face("/a.ttf", 0, "f", ["f"], "Regular", ["Regular"], 80, 0)
    second = Face("/b.ttf", 1, "f", ["f"], "Regular", ["Regular"], 80, 0)
    family = FamilyInfo("f", ["f"], [second, first])
    assert family.source_face.path == "/a.ttf"


def test_display_name_shows_cjk_alias():
    family = FamilyInfo("SimSun", ["SimSun", "宋体"], [])
    assert family.display_name == "SimSun (宋体)"


def test_display_name_without_alias():
    family = FamilyInfo("SimSun", ["SimSun"], [])
    assert family.display_name == "SimSun"


def test_location_for_collection():
    collection = Face("/a.ttc", 2, "f", ["f"], "Regular", ["Regular"], 80, 0)
    collection.is_collection = True
    assert collection.location == "/a.ttc#2"
    plain = Face("/a.ttf", 0, "f", ["f"], "Regular", ["Regular"], 80, 0)
    assert plain.location == "/a.ttf"
