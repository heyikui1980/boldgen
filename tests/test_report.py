"""输出格式化（report.py）的测试。

重点是**表格对齐**：家族名里混着中文（显示宽度 2 列），
如果按字符数算列宽，表格就会歪。
"""

from __future__ import annotations

import os

from boldgen.builder import BuildResult
from boldgen.discover import Face, FamilyInfo
from boldgen.report import (
    build_result_to_dict,
    family_to_dict,
    format_size,
    render_build_table,
    render_family_table,
)


def make_family(key, names=None, has_bold=False) -> FamilyInfo:
    face = Face(
        path=f"/usr/share/fonts/{key}.ttf",
        index=0,
        family=key,
        families=list(names or [key]),
        style="Regular",
        styles=["Regular"],
        weight=80,
        slant=0,
    )
    bold = Face(
        path=f"/usr/share/fonts/{key}-Bold.ttf",
        index=0,
        family=key,
        families=list(names or [key]),
        style="Bold",
        styles=["Bold"],
        weight=200,
        slant=0,
    )
    faces = [face, bold] if has_bold else [face]
    return FamilyInfo(
        key=key,
        names=list(names or [key]),
        faces=faces,
        is_cjk=True,
    )


def _display_width(text: str) -> int:
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024 * 10) == "10.0 MB"
    assert format_size(1024 ** 3) == "1.0 GB"


def test_family_table_columns_align():
    """各行的**列边界**必须对齐（中文占两列，所以要按显示宽度算）。"""
    families = [
        make_family("SimSun", ["SimSun", "宋体"]),
        make_family("AR PL UKai CN", ["AR PL UKai CN", "文鼎明体"]),
        make_family("FangSong", ["FangSong", "仿宋"]),
    ]
    table = render_family_table(families)
    lines = table.splitlines()
    assert len(lines) == len(families) + 2  # 表头 + 分隔线 + 数据行

    # 最后一列是源文件路径；找出它在每一行里的起始显示列，必须完全一致。
    offsets = set()
    for info, line in zip(families, lines[2:]):
        path = info.source_face.location
        offsets.add(_display_width(line[: line.rindex(path)]))
    assert len(offsets) == 1, f"源文件列的起始位置不一致：{offsets}"


def test_family_table_shows_status():
    families = [
        make_family("SimSun", ["SimSun", "宋体"]),
        make_family("NotoSans", ["NotoSans"], has_bold=True),
    ]
    table = render_family_table(families)
    assert "缺粗体" in table
    assert "有粗体" in table


def test_family_table_empty():
    assert render_family_table([]) == "（没有符合条件的字体家族）"


def test_build_table_columns_align():
    results = [
        BuildResult(output="/tmp/SimSun-Bold.ttf", num_glyphs=28862, radius=4, size=10 * 1024 * 1024),
        BuildResult(output="/tmp/宋体-Bold.ttf", num_glyphs=8192, radius=4, size=3 * 1024 * 1024),
    ]
    table = render_build_table(results)
    lines = table.splitlines()
    # 最后一列是文件名；各行的起始显示列必须一致。
    offsets = set()
    for result, line in zip(results, lines[2:]):
        name = os.path.basename(result.output)
        offsets.add(_display_width(line[: line.rindex(name)]))
    assert len(offsets) == 1, f"文件列的起始位置不一致：{offsets}"


def test_build_table_empty():
    assert render_build_table([]) == "（没有产物）"


def test_family_to_dict():
    info = make_family("SimSun", ["SimSun", "宋体"])
    data = family_to_dict(info)
    assert data["key"] == "SimSun"
    assert data["names"] == ["SimSun", "宋体"]
    assert data["is_cjk"] is True
    assert data["has_real_bold"] is False
    assert data["source"].endswith("SimSun.ttf")
    assert len(data["faces"]) == 1


def test_build_result_to_dict():
    result = BuildResult(
        output="/tmp/x.ttf",
        source="/tmp/y.ttf",
        face_index=1,
        family="X",
        num_glyphs=10,
        radius=4,
        size=100,
    )
    data = build_result_to_dict(result)
    assert data["output"] == "/tmp/x.ttf"
    assert data["face_index"] == 1
    assert data["family"] == "X"
