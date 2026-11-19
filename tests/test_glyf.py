"""``glyf`` 表解析与序列化的测试。"""

from __future__ import annotations

import struct

import pytest

from boldgen.glyf import (
    build_glyph,
    parse_glyph,
    parse_loca,
    serialize_glyph,
)
from boldgen.geometry import Contour, Glyph, Point

from conftest import DONUT, ROUND, SQUARE, WITH_IMPLIED


def _roundtrip(glyph: Glyph):
    blob = build_glyph(glyph)
    parsed = parse_glyph(blob, 0, len(blob))
    assert parsed is not None
    assert parsed.glyph is not None
    return parsed.glyph


def test_build_glyph_header():
    blob = build_glyph(SQUARE)
    contours, x_min, y_min, x_max, y_max = struct.unpack_from(">hhhhh", blob, 0)
    assert contours == 1
    assert (x_min, y_min, x_max, y_max) == (100, 0, 500, 400)


def test_build_glyph_empty_returns_nothing():
    assert build_glyph(Glyph([])) == b""


def test_roundtrip_square():
    out = _roundtrip(SQUARE)
    assert len(out.contours) == 1
    original = SQUARE.contours[0].points
    rebuilt = out.contours[0].points
    assert len(rebuilt) == len(original)
    for a, b in zip(original, rebuilt):
        assert (a.x, a.y) == pytest.approx((b.x, b.y))
        assert a.on == b.on


def test_roundtrip_donut_keeps_two_contours():
    out = _roundtrip(DONUT)
    assert len(out.contours) == 2


def test_roundtrip_round_keeps_off_curve_flags():
    out = _roundtrip(ROUND)
    rebuilt = out.contours[0].points
    original = ROUND.contours[0].points
    assert len(rebuilt) == len(original)
    assert [p.on for p in rebuilt] == [p.on for p in original]


def test_roundtrip_preserves_implicit_midpoint_structure():
    """两个连续 off-curve 点之间的隐含中点不是显式点，往返读写应当保持结构不变。

    隐含中点是在**读取之后**由 :func:`boldgen.geometry.resolve` 补出来的，
    ``parse_glyph`` 只负责忠实还原文件里的点结构。
    """
    out = _roundtrip(WITH_IMPLIED)
    rebuilt = out.contours[0].points
    assert len(rebuilt) == len(WITH_IMPLIED.contours[0].points) == 5
    assert [p.on for p in rebuilt] == [p.on for p in WITH_IMPLIED.contours[0].points]
    # 两个 off-curve 点仍然相邻
    assert not rebuilt[2].on and not rebuilt[3].on


def test_parse_glyph_empty_offset_returns_none():
    assert parse_glyph(b"", 0, 0) is None


def test_parse_glyph_out_of_range_returns_none():
    assert parse_glyph(b"\x00" * 20, 100, 20) is None


def test_large_delta_uses_int16():
    """坐标差超过 255 时必须走 int16 路径，而不是被截断。"""
    contour = Contour(
        [Point(0, 0, True), Point(1000, 0, True), Point(1000, 1000, True), Point(0, 1000, True)]
    )
    out = _roundtrip(Glyph([contour]))
    rebuilt = out.contours[0].points
    assert (rebuilt[1].x, rebuilt[1].y) == pytest.approx((1000.0, 0.0))
    assert (rebuilt[2].x, rebuilt[2].y) == pytest.approx((1000.0, 1000.0))


def test_negative_delta_uses_int16():
    contour = Contour(
        [Point(-800, -600, True), Point(0, 0, True), Point(800, 0, True), Point(0, 700, True)]
    )
    out = _roundtrip(Glyph([contour]))
    rebuilt = out.contours[0].points
    assert (rebuilt[0].x, rebuilt[0].y) == pytest.approx((-800.0, -600.0))


def test_repeat_flag_is_compressed_and_expanded():
    """同 flag 的连续点应当被 REPEAT 压缩，但解析后要完整还原。"""
    points = [Point(i * 10, 0, True) for i in range(20)]
    blob = build_glyph(Glyph([Contour(points)]))
    out = _roundtrip(Glyph([Contour(points)]))
    assert len(out.contours[0].points) == 20
    # flag 流比点数少（说明确实用了 REPEAT）
    assert len(blob) < 10 + 2 + 2 + 20 + 40


def _composite_bytes(components):
    """构造一个复合字形的原始字节。"""
    out = struct.pack(">hhhhh", -1, 0, 0, 1000, 1000)
    for index, (glyph_index, dx, dy) in enumerate(components):
        flags = 0x0001 | 0x0002  # ARG_1_AND_2_ARE_WORDS | ARGS_ARE_XY_VALUES
        if index < len(components) - 1:
            flags |= 0x0020  # MORE_COMPONENTS
        out += struct.pack(">HHhh", flags, glyph_index, dx, dy)
    return out


def test_parse_composite_glyph():
    blob = _composite_bytes([(3, 10, 20), (5, -30, 40)])
    parsed = parse_glyph(blob, 0, len(blob))
    assert parsed is not None
    assert parsed.is_composite
    assert len(parsed.components) == 2
    assert parsed.components[0].glyph_index == 3
    assert (parsed.components[0].arg1, parsed.components[0].arg2) == (10, 20)
    assert parsed.components[1].glyph_index == 5
    assert (parsed.components[1].arg1, parsed.components[1].arg2) == (-30, 40)


def test_serialize_composite_roundtrip():
    blob = _composite_bytes([(3, 10, 20), (5, -30, 40)])
    parsed = parse_glyph(blob, 0, len(blob))
    again = serialize_glyph(parsed)
    parsed2 = parse_glyph(again, 0, len(again))
    assert parsed2 is not None
    assert parsed2.is_composite
    assert [c.glyph_index for c in parsed2.components] == [3, 5]
    assert (parsed2.components[1].arg1, parsed2.components[1].arg2) == (-30, 40)


def test_parse_loca_short_format():
    raw = struct.pack(">HHH", 0, 2, 4)  # 字节偏移 = 值 * 2
    assert parse_loca(raw, 0, 2) == [0, 4, 8]


def test_parse_loca_long_format():
    raw = struct.pack(">III", 0, 10, 30)
    assert parse_loca(raw, 1, 2) == [0, 10, 30]


def test_parse_loca_pads_short_table():
    assert parse_loca(b"\x00\x00", 1, 3) == [0, 0, 0, 0]
