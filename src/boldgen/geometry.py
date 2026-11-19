"""轮廓几何：中性表示与合成粗体（轮廓外扩）算法。

本模块**不依赖任何字体解析库**，只处理抽象的轮廓点，因此可以被独立测试，
也可以被替换成基于 fontTools 的实现。

坐标系
------
TrueType 使用 y 轴向上的坐标系。规范要求：

* **外轮廓**（外圈）按顺时针排列；
* **内孔**（洞）按逆时针排列。

对一个轮廓做"朝远离填充区域一侧"的偏移时，外轮廓向外膨胀、内孔向内收缩，
两者都让笔画变粗。沿切线 ``t`` 旋转 90° 得到法线 ``rot90(t) = (-t.y, t.x)``，
恰好对上述两类轮廓都指向远离填充区域的一侧（TrueType 的填充规则是
non-zero winding）。

本实现与 FreeType 的 ``FT_Outline_Embolden`` 思路一致，但做了两处改进：

1. **斜接失败退化为斜切（bevel）**，而不是把 miter 长度钳到上限形成长尖刺；
2. 支持把 TrueType 的**隐含 on-curve 中点物化**为显式点，从而精确地对齐
   拐角处的接缝（见 :func:`embolden` 的 ``materialize`` 参数）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "Point",
    "Contour",
    "Glyph",
    "resolve",
    "tangents",
    "offset_point",
    "embolden",
    "contour_area",
    "glyph_area",
]

#: 数值比较的 epsilon。
_EPS = 1e-9


@dataclass
class Point:
    """轮廓上的一个点。

    Attributes:
        x, y: 坐标（浮点，单位为字体单位）。
        on: True 表示 on-curve（控制点为 False）。
        implicit: True 表示这是两个连续 off-curve 点之间**隐含**的
            on-curve 中点。源字体里它并不以显式点存在，
            读取器需要在 ``resolve()`` 里补出来。
    """

    x: float
    y: float
    on: bool = True
    implicit: bool = False

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Contour:
    """一条闭合轮廓。"""

    points: List[Point] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self):
        return iter(self.points)


@dataclass
class Glyph:
    """一个字形：若干条轮廓。

    空轮廓列表表示空白字形（``.notdef`` 之类）。
    """

    contours: List[Contour] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.contours)

    @property
    def is_empty(self) -> bool:
        return not any(c.points for c in self.contours)

    def bbox(self) -> Optional[Tuple[float, float, float, float]]:
        """返回 (xMin, yMin, xMax, yMax)；空字形返回 None。"""
        xs: List[float] = []
        ys: List[float] = []
        for c in self.contours:
            for p in c.points:
                xs.append(p.x)
                ys.append(p.y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------
# 基础向量运算
# --------------------------------------------------------------------------

def _norm(v: Tuple[float, float]) -> Tuple[float, float]:
    """归一化；零向量返回 (0, 0)。"""
    x, y = v
    length = math.hypot(x, y)
    if length < _EPS:
        return (0.0, 0.0)
    return (x / length, y / length)


def _rot90(t: Tuple[float, float]) -> Tuple[float, float]:
    """逆时针旋转 90°：``(-t.y, t.x)``。"""
    return (-t[1], t[0])


# --------------------------------------------------------------------------
# 隐含中点
# --------------------------------------------------------------------------

def resolve(contour: Sequence[Point]) -> List[Point]:
    """把 TrueType 的隐含 on-curve 中点补成显式点。

    TrueType 规定：两个**连续**的 off-curve 控制点之间，隐含一个 on-curve 点，
    位置是这两点的中点。

    本函数按此规则在环上插入这些中点，返回的序列严格满足
    "任意两个相邻 on-curve 点之间最多只有一个 off-curve 点"。

    插入的中点带 ``implicit=True`` 标记，便于调用方决定是否物化。
    """
    pts = list(contour)
    n = len(pts)
    if n < 2:
        return pts

    out: List[Point] = []
    for i in range(n):
        cur = pts[i]
        nxt = pts[(i + 1) % n]
        out.append(cur)
        if not cur.on and not nxt.on:
            out.append(
                Point((cur.x + nxt.x) / 2.0, (cur.y + nxt.y) / 2.0, on=True, implicit=True)
            )
    return out


# --------------------------------------------------------------------------
# 切线
# --------------------------------------------------------------------------

def tangents(seq: Sequence[Point]) -> List[Optional[Tuple[Tuple[float, float], Tuple[float, float]]]]:
    """计算序列中每个点的 ``(t_in, t_out)``。

    * on-curve 点：取真实曲线在该点的切线。
      - 入向切线来自**紧邻的前一个 off-curve 控制点**（若有），
        否则退化为"上一个 on-curve 锚点 → 本点"的方向；
      - 出向切线对称。
    * off-curve 点：取控制多边形两条边的方向，
      即"上一个 on-curve 锚点 → 本点"与"本点 → 下一个 on-curve 锚点"。

    要求 ``seq`` 已经过 :func:`resolve` 处理。
    返回的列表中，off-curve 位置为 ``None``（它们没有独立的入/出切线槽位）。
    """
    n = len(seq)
    result: List[Optional[Tuple[Tuple[float, float], Tuple[float, float]]]] = [None] * n
    if n == 0:
        return result

    on_idx = [i for i, p in enumerate(seq) if p.on]
    if not on_idx:
        return result
    m = len(on_idx)

    for k in range(m):
        i = on_idx[k]
        ip = on_idx[(k - 1) % m]
        inx = on_idx[(k + 1) % m]
        p = seq[i]

        # 入向切线
        j = (i - 1) % n
        if j != i and not seq[j].on:
            t_in = _norm((p.x - seq[j].x, p.y - seq[j].y))
        else:
            t_in = _norm((p.x - seq[ip].x, p.y - seq[ip].y))

        # 出向切线
        j = (i + 1) % n
        if j != i and not seq[j].on:
            t_out = _norm((seq[j].x - p.x, seq[j].y - p.y))
        else:
            t_out = _norm((seq[inx].x - p.x, seq[inx].y - p.y))

        result[i] = (t_in, t_out)

        # 本锚点与下一个锚点之间最多一个 off-curve 点
        j = (i + 1) % n
        guard = 0
        while j != inx and guard <= n:
            c = seq[j]
            result[j] = (
                _norm((c.x - p.x, c.y - p.y)),
                _norm((seq[inx].x - c.x, seq[inx].y - c.y)),
            )
            j = (j + 1) % n
            guard += 1

    return result


# --------------------------------------------------------------------------
# 偏移
# --------------------------------------------------------------------------

def _bevel(
    p: Point, n_in: Tuple[float, float], n_out: Tuple[float, float], r: float
) -> List[Tuple[float, float]]:
    """斜切（bevel）连接：返回两个点，把原来的拐角"削平"。"""
    return (
        (p.x + n_in[0] * r, p.y + n_in[1] * r),
        (p.x + n_out[0] * r, p.y + n_out[1] * r),
    )


def offset_point(
    p: Point,
    t_in: Tuple[float, float],
    t_out: Tuple[float, float],
    r: float,
    miter_limit: float = 4.0,
) -> List[Tuple[float, float]]:
    """把点 ``p`` 沿轮廓外法线偏移 ``r``。

    返回 1 个点（普通斜接）或 2 个点（斜切退化的拐角）。

    算法
    ----
    设入/出法线为 ``n1`` / ``n2``，其角平分方向为 ``m``，
    则斜接长度为 ``r / cos(θ/2)``，其中 ``θ`` 是两法线夹角。

    * ``cos(θ/2) <= 0``（两法线几乎相反，即 180° 折返的尖角）→ 斜切。
    * 斜接长度超过 ``r * miter_limit`` → 斜切（SVG/PostScript 的标准行为）。
      早期实现在这里把长度**钳到上限**，会在凹角处留下一根 ``miter_limit`` 倍
      半径的长尖刺，是最显眼的伪影来源。

    ``p`` 是 off-curve 控制点时不做斜切退化——那会在曲线中间插入 on-curve 点，
    破坏二次曲线结构；此时退化为"保持钳制"。
    """
    n1 = _rot90(t_in)
    n2 = _rot90(t_out)

    if n1 == (0.0, 0.0) and n2 == (0.0, 0.0):
        return [(p.x, p.y)]
    if n1 == (0.0, 0.0):
        n1 = n2
    if n2 == (0.0, 0.0):
        n2 = n1

    mx, my = n1[0] + n2[0], n1[1] + n2[1]
    mlen = math.hypot(mx, my)
    if mlen < _EPS:
        # 两法线完全相反：180° 折返
        if p.on:
            return _bevel(p, n1, n2, r)
        return [(p.x, p.y)]

    mdir = (mx / mlen, my / mlen)
    cos_half = mdir[0] * n1[0] + mdir[1] * n1[1]

    if cos_half <= _EPS:
        if p.on:
            return _bevel(p, n1, n2, r)
        return [(p.x, p.y)]

    miter = r / cos_half
    if miter > r * miter_limit:
        if p.on:
            return _bevel(p, n1, n2, r)
        return [(p.x + mdir[0] * r * miter_limit, p.y + mdir[1] * r * miter_limit)]

    return [(p.x + mdir[0] * miter, p.y + mdir[1] * miter)]


def _offset_contour(
    contour: Sequence[Point],
    r: float,
    miter_limit: float,
    materialize: bool,
) -> List[Point]:
    """把一条轮廓向外偏移 ``r``，返回新的点序列。

    ``materialize=True`` 时，隐含中点会被写成显式的 on-curve 点；
    ``False`` 时隐含中点被丢弃（由写出阶段按规则重新隐含），文件更小、
    与源字体的点结构完全一致，但拐角处的接缝会有二阶误差。
    """
    seq = resolve(contour)
    if len(seq) < 2 or r <= 0:
        return [Point(p.x, p.y, p.on, False) for p in seq]

    # 旋转到以 on-curve 点开头（写出时要求轮廓首点为 on-curve）
    start = next((i for i, p in enumerate(seq) if p.on), None)
    if start is None:
        return [Point(p.x, p.y, p.on, False) for p in seq]
    seq = seq[start:] + seq[:start]

    tans = tangents(seq)
    out: List[Point] = []
    for i, p in enumerate(seq):
        if p.implicit and not materialize:
            continue
        t = tans[i]
        if t is None:
            out.append(Point(p.x, p.y, p.on, False))
            continue
        t_in, t_out = t
        for (x, y) in offset_point(p, t_in, t_out, r, miter_limit):
            out.append(Point(x, y, p.on, False))

    if not out:
        return [Point(p.x, p.y, p.on, False) for p in seq]
    return out


def embolden(
    glyph: Glyph,
    r: float,
    miter_limit: float = 4.0,
    materialize: bool = True,
) -> Glyph:
    """返回加粗后的字形。

    Args:
        glyph: 源字形。
        r: 外扩半径，单位为字体单位（font units）。
        miter_limit: 斜接长度上限倍数，超过则退化为斜切。
        materialize: 是否把隐含 on-curve 中点物化为显式点。

    ``r <= 0`` 时原样返回（副本）。
    """
    if r <= 0:
        return Glyph(
            [
                Contour([Point(p.x, p.y, p.on, p.implicit) for p in c.points])
                for c in glyph.contours
            ]
        )
    return Glyph(
        [
            Contour(_offset_contour(c.points, r, miter_limit, materialize))
            for c in glyph.contours
        ]
    )


# --------------------------------------------------------------------------
# 面积（用于自检与回归测试）
# --------------------------------------------------------------------------

def contour_area(contour: Sequence[Point]) -> float:
    """用 shoelace 公式算轮廓的**有符号**面积。

    TrueType 外轮廓为顺时针（y 轴向上），有符号面积为负。
    """
    pts = resolve(contour)
    n = len(pts)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = pts[i].x, pts[i].y
        x2, y2 = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        total += x1 * y2 - x2 * y1
    return total / 2.0


def glyph_area(glyph: Glyph) -> float:
    """字形的净面积（有符号面积之和取绝对值）。"""
    total = 0.0
    for c in glyph.contours:
        total += contour_area(c.points)
    return abs(total)
