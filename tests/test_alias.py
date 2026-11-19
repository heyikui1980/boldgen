"""fontconfig 别名模式的测试。"""

from __future__ import annotations

import pytest

from boldgen.alias import (
    AliasRule,
    build_alias_xml,
    classify_family,
    load_rules,
    recommend_target,
    save_rules,
)
from boldgen.discover import Face, FamilyInfo


def _face(family, style="Regular", weight=80, slant=0, path="/tmp/x.ttf", index=0):
    return Face(
        path=path,
        index=index,
        family=family,
        families=[family],
        style=style,
        styles=[style],
        weight=weight,
        slant=slant,
    )


def _family(key, names, faces, is_cjk=True):
    return FamilyInfo(key=key, names=list(names), faces=list(faces), is_cjk=is_cjk)


def test_build_alias_xml_shape():
    xml = build_alias_xml([AliasRule("SimSun", "Noto Serif CJK SC")])
    assert "<match target=\"pattern\">" in xml
    assert "<test name=\"family\" compare=\"eq\">" in xml
    assert "<string>SimSun</string>" in xml
    assert "<const>bold</const>" in xml
    assert "<edit name=\"family\" mode=\"assign\">" in xml
    assert "<string>Noto Serif CJK SC</string>" in xml
    assert xml.rstrip().endswith("</fontconfig>")


def test_build_alias_xml_escapes():
    xml = build_alias_xml([AliasRule("A&B", "C<D")])
    assert "A&amp;B" in xml
    assert "C&lt;D" in xml


def test_rules_roundtrip(tmp_path):
    path = tmp_path / "aliases.conf"
    rules = [
        AliasRule("SimSun", "Noto Serif CJK SC"),
        AliasRule("SimHei", "Noto Sans CJK SC"),
    ]
    save_rules(rules, str(path))
    loaded = load_rules(str(path))
    assert [(r.source_family, r.target_family) for r in loaded] == [
        ("SimSun", "Noto Serif CJK SC"),
        ("SimHei", "Noto Sans CJK SC"),
    ]


def test_load_rules_on_missing_file(tmp_path):
    assert load_rules(str(tmp_path / "nope.conf")) == []


@pytest.mark.parametrize(
    "name,expected",
    [
        ("宋体", "song"),
        ("SimSun", "song"),
        ("黑体", "hei"),
        ("SimHei", "hei"),
        ("楷体", "kai"),
        ("KaiTi", "kai"),
        ("仿宋_GB2312", "fangsong"),
        ("FangSong", "fangsong"),
        ("华文隶书", "lishu"),
        ("Adobe Blank", "other"),
    ],
)
def test_classify_family(name, expected):
    assert classify_family(name) == expected


def test_recommend_target_prefers_same_category():
    source = _family("SimSun", ["SimSun", "宋体"], [_face("SimSun")])
    serif = _family(
        "Noto Serif CJK SC",
        ["Noto Serif CJK SC"],
        [_face("Noto Serif CJK SC", "Regular"), _face("Noto Serif CJK SC", "Bold", weight=200)],
    )
    sans = _family(
        "Noto Sans CJK SC",
        ["Noto Sans CJK SC"],
        [_face("Noto Sans CJK SC", "Regular"), _face("Noto Sans CJK SC", "Bold", weight=200)],
    )
    target = recommend_target(source, [source, serif, sans])
    assert target is not None
    assert target.key == "Noto Serif CJK SC"


def test_recommend_target_requires_real_bold():
    source = _family("SimSun", ["SimSun"], [_face("SimSun")])
    no_bold = _family("Only Regular", ["Only Regular"], [_face("Only Regular")])
    assert recommend_target(source, [source, no_bold]) is None


def test_recommend_target_ignores_non_cjk():
    source = _family("SimSun", ["SimSun"], [_face("SimSun")])
    latin = _family(
        "DejaVu Sans",
        ["DejaVu Sans"],
        [_face("DejaVu Sans"), _face("DejaVu Sans", "Bold", weight=200)],
        is_cjk=False,
    )
    assert recommend_target(source, [source, latin]) is None


def test_recommend_target_never_returns_the_source():
    source = _family(
        "SimSun",
        ["SimSun"],
        [_face("SimSun"), _face("SimSun", "Bold", weight=200)],
    )
    assert recommend_target(source, [source]) is None
