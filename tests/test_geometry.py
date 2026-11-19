"""几何引擎的回归测试。"""

from __future__ import annotations

import math

import pytest

from boldgen.geometry import (
    Contour,
    Glyph,
    Point,
    contour_area,
    embolden,
    offset_point,
    resolve,
    tangents,
)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_resolve_inserts_implied_midpoint():
    contour = [Point(0, 0, True), Point(10, 0, False), Point(20, 0, False), Point(30, 0, True)]
    out = resolve(contour)
    assert len(out) == 5
    mids = [p for p in out if p.implicit]
    assert len(mids) == 1
    assert (mids[0].x, mids[0].y) == (15.0, 0.0)
    assert mids[0].on


def test_resolve_leaves_alternating_contour_untouched():
    contour = [Point(0, 0, True), Point(10, 0, False), Point(20, 0, True)]
    out = resolve(contour)
    assert len(out) == 3
    assert not any(p.implicit for p in out)


def test_resolve_is_cyclic():
    """首尾都是 off-curve 时，也要在环上补中点。"""
    contour = [Point(10, 0, False), Point(20, 0, False), Point(20, 10, True)]
    out = resolve(contour)
    assert any(p.implicit for p in out)


def test_tangents_on_square():
    # TrueType 外轮廓是顺时针（y 轴向上），因此逆时针的方框不会被外扩。
    square = [Point(0, 0, True), Point(0, 100, True), Point(100, 100, True), Point(100, 0, True)]
    tans = tangents(resolve(square))
    assert all(t is not None for t in tans)
    # 左下角：入向切线来自上一个锚点 (100,0)，出向切线指向下一个锚点 (0,100)
    t_in, t_out = tans[0]
    assert t_in == pytest.approx((-1.0, 0.0), abs=1e-6)
    assert t_out == pytest.approx((0.0, 1.0), abs=1e-6)


def test_offset_point_miter_length():
    """90° 拐角的斜接长度应为 r / cos(45°)。"""
    p = Point(0, 0, True)
    # 入向 (1,0)、出向 (0,1)
    out = offset_point(p, (1.0, 0.0), (0.0, 1.0), 10.0, 4.0)
    assert len(out) == 1
    x, y = out[0]
    assert math.hypot(x, y) == pytest.approx(10.0 / math.cos(math.pi / 4), rel=1e-6)


def test_offset_point_bevels_on_reversal():
    """180° 折返必须退化成斜切（两个点），不能是长尖刺。"""
    p = Point(0, 0, True)
    out = offset_point(p, (1.0, 0.0), (-1.0, 0.0), 10.0, 4.0)
    assert len(out) == 2
    for x, y in out:
        assert math.hypot(x, y) == pytest.approx(10.0, rel=1e-6)


def test_offset_point_bevels_when_miter_exceeds_limit():
    """斜接长度超过上限时退化为斜切。"""
    p = Point(0, 0, True)
    # 出向几乎与入向相反 → 夹角接近 180° → 斜接长度发散
    # （两个切线都是单位向量，模长 1）
    out = offset_point(p, (1.0, 0.0), (-0.96, 0.28), 10.0, 4.0)
    assert len(out) == 2
    for x, y in out:
        assert math.hypot(x, y) == pytest.approx(10.0, rel=1e-6)


def test_embolden_grows_outer_contour():
    """顺时针的外轮廓应当变大。"""
    square = Contour(
        [Point(0, 0, True), Point(0, 100, True), Point(100, 100, True), Point(100, 0, True)]
    )
    before = abs(contour_area(square))
    after = abs(contour_area(embolden(Glyph([square]), 10.0).contours[0]))
    assert after > before


def test_embolden_shrinks_hole():
    """逆时针的内孔应当变小。"""
    outer = Contour(
        [Point(0, 0, True), Point(0, 100, True), Point(100, 100, True), Point(100, 0, True)]
    )
    hole = Contour(
        [Point(20, 20, True), Point(80, 20, True), Point(80, 80, True), Point(20, 80, True)]
    )
    bold = embolden(Glyph([outer, hole]), 10.0)
    assert abs(contour_area(bold.contours[0])) > 100 * 100
    assert abs(contour_area(bold.contours[1])) < 60 * 60


def test_embolden_no_long_spikes():
    """关键回归：偏移后的点不能离原顶点太远（旧实现会冒出一根 4r 的尖刺）。

    轮廓在 (60,0) 处折返——入向与出向几乎相反，这正是旧实现把 miter
    钳到 4r 之后长出尖刺的地方。
    """
    contour = Contour(
        [
            Point(0, 0, True),
            Point(0, 100, True),
            Point(100, 100, True),
            Point(100, 0, True),
            Point(60, 0, True),    # 折返
            Point(100, 2, True),
        ]
    )
    radius = 10.0
    bold = embolden(Glyph([contour]), radius, miter_limit=4.0)
    sources = [(p.x, p.y) for p in contour.points]
    for point in bold.contours[0].points:
        nearest = min(_dist((point.x, point.y), s) for s in sources)
        assert nearest <= radius * 1.5, f"点 {point} 离原轮廓过远：{nearest}"


def test_embolden_bevel_inserts_extra_points():
    """折返处应当被斜切（插入额外的点），而不是留一个长尖刺。"""
    contour = Contour(
        [
            Point(0, 0, True),
            Point(0, 100, True),
            Point(100, 100, True),
            Point(100, 0, True),
            Point(60, 0, True),    # 折返
            Point(100, 2, True),
        ]
    )
    bold = embolden(Glyph([contour]), 10.0, miter_limit=4.0)
    # 6 个源点；折返处被斜切成两个点，因此点数增加
    assert len(bold.contours[0].points) > len(contour.points)


def test_embolden_materialize_adds_explicit_midpoint():
    contour = Contour(
        [
            Point(0, 0, True),
            Point(50, 0, False),
            Point(100, 0, False),
            Point(100, 100, True),
            Point(0, 100, True),
        ]
    )
    with_mid = embolden(Glyph([contour]), 5.0, materialize=True)
    without_mid = embolden(Glyph([contour]), 5.0, materialize=False)
    assert len(with_mid.contours[0].points) == len(contour.points) + 1
    assert len(without_mid.contours[0].points) == len(contour.points)


def test_embolden_preserves_point_count_without_materialize():
    square = Contour(
        [Point(0, 0, True), Point(100, 0, True), Point(100, 100, True), Point(0, 100, True)]
    )
    bold = embolden(Glyph([square]), 5.0, materialize=False)
    assert len(bold.contours[0].points) == len(square.points)


def test_embolden_zero_radius_is_noop():
    square = Contour([Point(0, 0, True), Point(100, 0, True)])
    bold = embolden(Glyph([square]), 0.0)
    assert len(bold.contours[0].points) == 2
    assert (bold.contours[0].points[0].x, bold.contours[0].points[0].y) == (0, 0)


def test_embolden_empty_glyph():
    bold = embolden(Glyph([]), 10.0)
    assert bold.is_empty
