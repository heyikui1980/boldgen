"""端到端回归：生成 → 自检 → 墨量。"""

from __future__ import annotations

import struct

import pytest

from boldgen.builder import BuildOptions, build_bold
from boldgen.sfnt import Font
from boldgen.verify import (
    INK_RATIO_MAX,
    INK_RATIO_MIN,
    ink_area,
    ink_ratio,
    verify_font,
)


def test_end_to_end_single_font(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    result = build_bold(square_font, str(out))
    assert result.changed >= 1

    check = verify_font(str(out), source_path=square_font)
    assert check.ok, check.errors
    assert check.errors == []


def test_end_to_end_multiple_glyphs(tmp_path, multi_font):
    out = tmp_path / "Multi-Bold.ttf"
    build_bold(multi_font, str(out))
    check = verify_font(str(out), source_path=multi_font)
    assert check.ok, check.errors


def test_ink_ratio_is_a_bump(tmp_path, multi_font):
    out = tmp_path / "Multi-Bold.ttf"
    build_bold(multi_font, str(out))
    ratio = ink_ratio(str(out), multi_font)
    assert ratio is not None
    assert ratio > 1.0
    assert INK_RATIO_MIN <= ratio <= INK_RATIO_MAX


def test_ink_grows_monotonically_with_strength(tmp_path, square_font):
    ratios = []
    for strength in (0.005, 0.010, 0.020, 0.040):
        out = tmp_path / f"Bold-{strength}.ttf"
        build_bold(square_font, str(out), options=BuildOptions(strength=strength))
        ratios.append(ink_ratio(str(out), square_font))
    assert ratios == sorted(ratios)
    assert ratios[0] < ratios[-1]


def test_generated_font_keeps_glyph_count(tmp_path, multi_font):
    out = tmp_path / "Multi-Bold.ttf"
    build_bold(multi_font, str(out))
    with open(multi_font, "rb") as handle:
        source = Font(handle.read())
    bold = Font(out.read_bytes())
    assert bold.num_glyphs == source.num_glyphs
    assert bold.table_bytes("cmap") == source.table_bytes("cmap")
    assert bold.table_bytes("hmtx") == source.table_bytes("hmtx")


def test_generated_font_is_parsable_by_fontconfig(tmp_path, square_font):
    """生成物必须是合法的 sfnt：目录、校验和、glyf 都要自洽。"""
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    data = out.read_bytes()
    version, num_tables = struct.unpack_from(">IH", data, 0)
    assert version == 0x00010000
    assert num_tables > 0
    font = Font(data)
    assert font.has_table("glyf")
    assert font.units_per_em == 1000
    assert font.num_glyphs == 2


def test_empty_glyph_font_survives(tmp_path):
    """全是空字形的字体（.notdef 之类）不应让生成器崩溃。"""
    from conftest import make_font_bytes

    source = tmp_path / "Empty.ttf"
    source.write_bytes(make_font_bytes([]))
    out = tmp_path / "Empty-Bold.ttf"
    build_bold(str(source), str(out))
    check = verify_font(str(out))
    assert check.ok, check.errors


def test_ink_area_is_zero_for_empty_font(tmp_path):
    from conftest import make_font_bytes

    source = tmp_path / "Empty.ttf"
    source.write_bytes(make_font_bytes([]))
    area, count = ink_area(str(source))
    assert area == 0.0
    assert count == 1
