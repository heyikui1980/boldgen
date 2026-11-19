"""测试夹具：用内置 writer 现场构造最小 TrueType 字体。

不依赖系统里装的任何字体文件，因此测试在任何机器上结果都一致。
"""

from __future__ import annotations

import struct
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from boldgen.glyf import build_glyph
from boldgen.geometry import Contour, Glyph, Point
from boldgen.sfnt import NameRecord, build_name_table, write_sfnt


def make_contour(points: Sequence[Tuple[float, float, bool]]) -> Contour:
    """``[(x, y, on_curve), ...]`` → Contour。"""
    return Contour([Point(x, y, on) for x, y, on in points])


def make_glyph(contours: Sequence[Contour]) -> Glyph:
    return Glyph(list(contours))


#: 一个 1000 upem 的方框字形。
#:
#: 注意**外轮廓按顺时针排列**——这是 TrueType 规范的要求，也是加粗算法
#: 判断"往外扩"还是"往里缩"的依据。
SQUARE = make_glyph(
    [
        make_contour(
            [(100, 0, True), (100, 400, True), (500, 400, True), (500, 0, True)]
        )
    ]
)

#: 一个外轮廓（顺时针）+ 一个内孔（逆时针）的字形。
DONUT = make_glyph(
    [
        make_contour(
            [(100, 0, True), (100, 400, True), (500, 400, True), (500, 0, True)]
        ),
        make_contour(
            [(200, 100, True), (400, 100, True), (400, 300, True), (200, 300, True)]
        ),
    ]
)

#: 带二次曲线控制点的字形（一个"圆"），顺时针。
ROUND = make_glyph(
    [
        make_contour(
            [
                (0, 300, True),
                (0, 466, False),
                (134, 600, False),
                (300, 600, True),
                (466, 600, False),
                (600, 466, False),
                (600, 300, True),
                (600, 134, False),
                (466, 0, False),
                (300, 0, True),
                (134, 0, False),
                (0, 134, False),
            ]
        )
    ]
)

#: 两个连续 off-curve 控制点（会触发隐含中点），顺时针。
WITH_IMPLIED = make_glyph(
    [
        make_contour(
            [
                (100, 400, True),
                (300, 400, True),
                (400, 300, False),
                (200, 100, False),
                (100, 100, True),
            ]
        )
    ]
)


def _relocate_sfnt(blob: bytes, base: int) -> bytes:
    """把 sfnt 内部各表的偏移改成**绝对**偏移。

    独立 sfnt 文件里，表目录里的 offset 是相对文件开头的；
    而在 TTC 里，它必须是相对**整个 .ttc 文件**开头的绝对偏移。
    """
    data = bytearray(blob)
    num_tables = struct.unpack_from(">H", data, 4)[0]
    pos = 12
    for _ in range(num_tables):
        offset = struct.unpack_from(">I", data, pos + 8)[0]
        struct.pack_into(">I", data, pos + 8, offset + base)
        pos += 16
    return bytes(data)


def make_ttc_bytes(fonts: Sequence[bytes]) -> bytes:
    """把多个 sfnt 打包成 TrueType Collection（.ttc）。

    每个 face 的表数据独立存放（真实字体常常共享，但那样对测试没好处）。
    """
    num = len(fonts)
    if num == 0:
        raise ValueError("至少要有一个 face")
    header_size = 12 + 4 * num
    offsets = []
    pos = header_size
    for blob in fonts:
        offsets.append(pos)
        pos += len(blob)
    out = bytearray()
    out += b"ttcf" + struct.pack(">II", 0x00010000, num)
    out += struct.pack(f">{num}I", *offsets)
    for base, blob in zip(offsets, fonts):
        out += _relocate_sfnt(blob, base)
    return bytes(out)


def _head_table(units_per_em: int, index_to_loc_format: int, bbox) -> bytes:
    x_min, y_min, x_max, y_max = bbox
    blob = bytearray(54)
    struct.pack_into(">I", blob, 0, 0x00010000)   # version
    struct.pack_into(">I", blob, 4, 0x00010000)   # fontRevision
    struct.pack_into(">I", blob, 8, 0)            # checkSumAdjustment
    struct.pack_into(">I", blob, 12, 0x5F0F3CF5)  # magicNumber
    struct.pack_into(">H", blob, 16, 0x000B)      # flags
    struct.pack_into(">H", blob, 18, units_per_em)
    struct.pack_into(">h", blob, 36, x_min)
    struct.pack_into(">h", blob, 38, y_min)
    struct.pack_into(">h", blob, 40, x_max)
    struct.pack_into(">h", blob, 42, y_max)
    struct.pack_into(">H", blob, 44, 0)           # macStyle
    struct.pack_into(">H", blob, 46, 8)           # lowestRecPPEM
    struct.pack_into(">h", blob, 48, 2)           # fontDirectionHint
    struct.pack_into(">h", blob, 50, index_to_loc_format)
    struct.pack_into(">h", blob, 52, 0)           # glyphDataFormat
    return bytes(blob)


def _maxp_table(num_glyphs: int, max_points: int, max_contours: int) -> bytes:
    blob = bytearray(32)
    struct.pack_into(">I", blob, 0, 0x00010000)
    struct.pack_into(">H", blob, 4, num_glyphs)
    struct.pack_into(">H", blob, 6, max_points)
    struct.pack_into(">H", blob, 8, max_contours)
    return bytes(blob)


def _hhea_table(num_glyphs: int) -> bytes:
    blob = bytearray(36)
    struct.pack_into(">I", blob, 0, 0x00010000)
    struct.pack_into(">h", blob, 4, 800)      # ascender
    struct.pack_into(">h", blob, 6, -200)     # descender
    struct.pack_into(">h", blob, 8, 0)        # lineGap
    struct.pack_into(">H", blob, 10, 1000)    # advanceWidthMax
    struct.pack_into(">h", blob, 12, 0)       # minLeftSideBearing
    struct.pack_into(">h", blob, 14, 0)       # minRightSideBearing
    struct.pack_into(">h", blob, 16, 1000)    # xMaxExtent
    struct.pack_into(">h", blob, 18, 1)       # caretSlopeRise
    struct.pack_into(">h", blob, 20, 0)       # caretSlopeRun
    struct.pack_into(">h", blob, 22, 0)       # caretOffset
    struct.pack_into(">h", blob, 32, 0)       # metricDataFormat
    struct.pack_into(">H", blob, 34, num_glyphs)
    return bytes(blob)


def _os2_table(weight: int = 400) -> bytes:
    blob = bytearray(96)
    struct.pack_into(">H", blob, 0, 1)         # version
    struct.pack_into(">H", blob, 2, 500)       # xAvgCharWidth
    struct.pack_into(">H", blob, 4, weight)    # usWeightClass
    struct.pack_into(">H", blob, 6, 5)         # usWidthClass
    struct.pack_into(">H", blob, 8, 0)         # fsType
    struct.pack_into(">h", blob, 10, 650)      # sTypoAscender 会被覆盖
    struct.pack_into(">H", blob, 62, 0x0040)   # fsSelection = REGULAR
    struct.pack_into(">h", blob, 68, 800)      # sTypoAscender
    struct.pack_into(">h", blob, 70, -200)     # sTypoDescender
    struct.pack_into(">H", blob, 74, 800)      # usWinAscent
    struct.pack_into(">H", blob, 76, 200)      # usWinDescent
    struct.pack_into(">H", blob, 86, 500)      # sxHeight
    struct.pack_into(">H", blob, 88, 700)      # sCapHeight
    return bytes(blob)


def _post_table() -> bytes:
    return struct.pack(
        ">IihhIIIII",
        0x00030000, 0, -100, 50, 0, 0, 0, 0, 0,
    )


def _cmap_table() -> bytes:
    """只有一个 segment 的 format 4 子表，把 'A'(0x41) 映射到 gid 1。"""
    seg_count = 2
    subtable = struct.pack(
        ">HHHHHHH",
        4,               # format
        0,               # length（后面补）
        0,               # language
        seg_count * 2,   # segCountX2
        2,               # searchRange
        0,               # entrySelector
        0,               # rangeShift
    )
    subtable += struct.pack(">H", 0x0041) + struct.pack(">H", 0xFFFF)  # endCode
    subtable += struct.pack(">H", 0)                                    # reservedPad
    subtable += struct.pack(">H", 0x0041) + struct.pack(">H", 0xFFFF)  # startCode
    subtable += struct.pack(">h", 1 - 0x41) + struct.pack(">h", 1)      # idDelta
    subtable += struct.pack(">H", 0) + struct.pack(">H", 0)            # idRangeOffset
    subtable = struct.pack(">H", len(subtable)) + subtable[2:]

    header = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 1, 12)
    return header + subtable


def make_font_bytes(
    glyphs: Sequence[Glyph],
    family: str = "TestFamily",
    style: str = "Regular",
    units_per_em: int = 1000,
    weight: int = 400,
    extra_tables: Optional[Dict[str, bytes]] = None,
) -> bytes:
    """构造一个最小可用的 TrueType 字体。

    第一个字形是 ``.notdef``（空），其余是给定的字形。
    """
    all_glyphs: List[Glyph] = [Glyph([])] + list(glyphs)

    glyf = bytearray()
    loca = bytearray()
    max_points = 0
    max_contours = 0
    for glyph in all_glyphs:
        blob = build_glyph(glyph)
        loca += struct.pack(">I", len(glyf))
        glyf += blob
        glyf += b"\x00" * ((-len(blob)) % 4)
        max_points = max(max_points, sum(len(c.points) for c in glyph.contours))
        max_contours = max(max_contours, len(glyph.contours))
    loca += struct.pack(">I", len(glyf))

    num_glyphs = len(all_glyphs)
    names = build_name_table(
        [
            NameRecord(3, 1, 0x0409, 1, family),
            NameRecord(3, 1, 0x0409, 5, "Version 1.000"),
        ],
        style=style,
        postscript_name=f"{family}-{style}",
    )

    tables = {
        "head": _head_table(units_per_em, 1, (0, 0, 1000, 1000)),
        "maxp": _maxp_table(num_glyphs, max_points, max_contours),
        "hhea": _hhea_table(num_glyphs),
        "hmtx": struct.pack(">Hh", 600, 0) * num_glyphs,
        "OS/2": _os2_table(weight),
        "name": names,
        "post": _post_table(),
        "cmap": _cmap_table(),
        "glyf": bytes(glyf),
        "loca": bytes(loca),
    }
    if extra_tables:
        tables.update(extra_tables)
    return write_sfnt(tables)


@pytest.fixture
def square_font(tmp_path):
    path = tmp_path / "Square.ttf"
    path.write_bytes(make_font_bytes([SQUARE]))
    return str(path)


@pytest.fixture
def multi_font(tmp_path):
    path = tmp_path / "Multi.ttf"
    path.write_bytes(make_font_bytes([SQUARE, DONUT, ROUND, WITH_IMPLIED]))
    return str(path)


#: 会被生成器剥掉的表（hinting / 位图 / 签名）。
STRIPPABLE = {
    "fpgm": b"\xb0\x01\x00\x00",
    "prep": b"\xb0\x01\x00\x00",
    "cvt ": b"\x00\x00\x00\x00",
    "EBDT": b"\x00" * 16,
    "EBLC": b"\x00" * 16,
    "DSIG": b"\x00" * 16,
}


@pytest.fixture
def strippable_font(tmp_path):
    """带 hinting / 位图 / 签名表的字体。"""
    path = tmp_path / "Strippable.ttf"
    path.write_bytes(make_font_bytes([SQUARE], extra_tables=dict(STRIPPABLE)))
    return str(path)


@pytest.fixture
def ttc_font(tmp_path):
    """两个 face 的 .ttc：face 0 = Square，face 1 = Donut。"""
    path = tmp_path / "Collection.ttc"
    path.write_bytes(
        make_ttc_bytes(
            [
                make_font_bytes([SQUARE], family="SquareFam"),
                make_font_bytes([DONUT], family="DonutFam"),
            ]
        )
    )
    return str(path)
