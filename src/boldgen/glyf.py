"""``glyf`` 表的解析与序列化，以及轮廓 ↔ 中性表示的互转。

``glyf`` 是 TrueType 的字形轮廓表。本模块负责：

* 解析简单字形（simple glyph）成 :class:`boldgen.geometry.Glyph`；
* 解析复合字形（composite glyph）成组件列表（**原样保留**，不做整体加粗）；
* 把中性表示重新序列化成 ``glyf`` 表内容。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .geometry import Contour, Glyph, Point

__all__ = [
    "CompositeComponent",
    "GlyphData",
    "parse_glyph",
    "build_glyph",
    "parse_loca",
    "serialize_glyph",
]

# --- 简单字形的 flag 位 ---------------------------------------------------
_ON_CURVE = 0x01
_X_SHORT = 0x02
_Y_SHORT = 0x04
_REPEAT = 0x08
_X_SAME = 0x10
_Y_SAME = 0x20

# --- 复合字形的 flag 位 ---------------------------------------------------
_ARG_1_AND_2_ARE_WORDS = 0x0001
_ARGS_ARE_XY_VALUES = 0x0002
_ROUND_XY_TO_GRID = 0x0004
_WE_HAVE_A_SCALE = 0x0008
_MORE_COMPONENTS = 0x0020
_WE_HAVE_AN_X_AND_Y_SCALE = 0x0040
_WE_HAVE_A_TWO_BY_TWO = 0x0080
_WE_HAVE_INSTRUCTIONS = 0x0100
_USE_MY_METRICS = 0x0200
_SCALED_COMPONENT_OFFSET = 0x0800
_UNSCALED_COMPONENT_OFFSET = 0x1000


@dataclass
class CompositeComponent:
    """复合字形的一个组件。"""

    glyph_index: int
    flags: int
    arg1: int
    arg2: int
    scale: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    instructions: bytes = b""

    @property
    def more(self) -> bool:
        return bool(self.flags & _MORE_COMPONENTS)


@dataclass
class GlyphData:
    """一个 ``glyf`` 表项的解析结果。"""

    number_of_contours: int
    x_min: int = 0
    y_min: int = 0
    x_max: int = 0
    y_max: int = 0
    glyph: Optional[Glyph] = None
    components: List[CompositeComponent] = field(default_factory=list)
    instructions: bytes = b""
    raw: bytes = b""

    @property
    def is_composite(self) -> bool:
        return self.number_of_contours < 0


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

def _decode_deltas(flags: Sequence[int], data: bytes, pos: int, short_bit: int,
                   same_bit: int) -> Tuple[List[int], int]:
    """按 TrueType 规则解码 delta 坐标，返回 (增量列表, 新位置)。

    ``flags`` 必须是**已经展开重复标志**的序列（见 :func:`parse_glyph`），
    所以这里不需要再处理 ``_REPEAT``。
    """
    deltas: List[int] = []
    for f in flags:
        if f & short_bit:
            if pos >= len(data):
                deltas.append(0)
                continue
            value = data[pos]
            pos += 1
            deltas.append(value if (f & same_bit) else -value)
        elif not (f & same_bit):
            if pos + 2 > len(data):
                deltas.append(0)
                continue
            value = struct.unpack_from(">h", data, pos)[0]
            pos += 2
            deltas.append(value)
        else:
            deltas.append(0)
    return deltas, pos


def parse_glyph(data: bytes, offset: int, length: int) -> Optional[GlyphData]:
    """解析 ``glyf`` 表中位于 ``offset`` 的一个字形。

    空字形（length == 0）返回 None。
    """
    if length <= 0 or offset + length > len(data):
        return None
    blob = data[offset : offset + length]
    if len(blob) < 10:
        return None

    number_of_contours, x_min, y_min, x_max, y_max = struct.unpack_from(">hhhhh", blob, 0)
    result = GlyphData(
        number_of_contours=number_of_contours,
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        raw=blob,
    )

    pos = 10
    if number_of_contours >= 0:
        # --- 简单字形 ---
        if pos + 2 * number_of_contours + 2 > len(blob):
            return None
        end_pts = list(
            struct.unpack_from(f">{number_of_contours}H", blob, pos)
        )
        pos += 2 * number_of_contours
        instruction_length = struct.unpack_from(">H", blob, pos)[0]
        pos += 2
        if pos + instruction_length > len(blob):
            return None
        result.instructions = blob[pos : pos + instruction_length]
        pos += instruction_length

        num_points = (end_pts[-1] + 1) if end_pts else 0

        # flags
        flags: List[int] = []
        while len(flags) < num_points and pos < len(blob):
            flag = blob[pos]
            pos += 1
            flags.append(flag)
            if flag & _REPEAT:
                if pos >= len(blob):
                    break
                count = blob[pos]
                pos += 1
                flags.extend([flag] * count)
        flags = flags[:num_points]

        xs, pos = _decode_deltas(flags, blob, pos, _X_SHORT, _X_SAME)
        ys, pos = _decode_deltas(flags, blob, pos, _Y_SHORT, _Y_SAME)

        abs_x: List[int] = []
        acc = 0
        for d in xs:
            acc += d
            abs_x.append(acc)
        abs_y: List[int] = []
        acc = 0
        for d in ys:
            acc += d
            abs_y.append(acc)

        contours: List[Contour] = []
        start = 0
        for end in end_pts:
            pts = [
                Point(float(abs_x[i]), float(abs_y[i]), on=bool(flags[i] & _ON_CURVE))
                for i in range(start, min(end + 1, num_points))
            ]
            contours.append(Contour(pts))
            start = end + 1
        result.glyph = Glyph(contours)
        return result

    # --- 复合字形 ---
    components: List[CompositeComponent] = []
    while True:
        if pos + 4 > len(blob):
            break
        flags, glyph_index = struct.unpack_from(">HH", blob, pos)
        pos += 4
        if flags & _ARG_1_AND_2_ARE_WORDS:
            arg1, arg2 = struct.unpack_from(">hh", blob, pos)
            pos += 4
        else:
            arg1, arg2 = struct.unpack_from(">bb", blob, pos)
            pos += 2
        scale = (1.0, 1.0, 1.0, 1.0)
        if flags & _WE_HAVE_A_SCALE:
            (s,) = struct.unpack_from(">h", blob, pos)
            pos += 2
            scale = (s / 16384.0, s / 16384.0, 1.0, 1.0)
        elif flags & _WE_HAVE_AN_X_AND_Y_SCALE:
            sx, sy = struct.unpack_from(">hh", blob, pos)
            pos += 4
            scale = (sx / 16384.0, sy / 16384.0, 1.0, 1.0)
        elif flags & _WE_HAVE_A_TWO_BY_TWO:
            a, b, c, d = struct.unpack_from(">hhhh", blob, pos)
            pos += 8
            scale = (a / 16384.0, b / 16384.0, c / 16384.0, d / 16384.0)

        components.append(
            CompositeComponent(
                glyph_index=glyph_index,
                flags=flags & ~_MORE_COMPONENTS,
                arg1=arg1,
                arg2=arg2,
                scale=scale,
            )
        )
        if not (flags & _MORE_COMPONENTS):
            break

    if components and (components[-1].flags & _WE_HAVE_INSTRUCTIONS):
        if pos + 2 <= len(blob):
            ilen = struct.unpack_from(">H", blob, pos)[0]
            pos += 2
            if pos + ilen <= len(blob):
                result.instructions = blob[pos : pos + ilen]

    result.components = components
    return result


def parse_loca(raw: bytes, index_to_loc_format: int, num_glyphs: int) -> List[int]:
    """解析 ``loca`` 表，返回长度 ``num_glyphs + 1`` 的偏移数组。"""
    offsets: List[int] = []
    if index_to_loc_format == 0:
        need = (num_glyphs + 1) * 2
        if len(raw) < need:
            raw = raw + b"\x00" * (need - len(raw))
        offsets = [v * 2 for v in struct.unpack_from(f">{num_glyphs + 1}H", raw, 0)]
    else:
        need = (num_glyphs + 1) * 4
        if len(raw) < need:
            raw = raw + b"\x00" * (need - len(raw))
        offsets = list(struct.unpack_from(f">{num_glyphs + 1}I", raw, 0))
    return offsets


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------

def _encode_deltas(values: Sequence[float], short_bit: int, same_bit: int) -> Tuple[List[int], bytes]:
    """把绝对坐标编码成 (flags 增量位, 字节流)。

    ``short_bit`` / ``same_bit`` 必须按坐标轴传入——X 用 0x02/0x10，
    Y 用 0x04/0x20。
    """
    flags: List[int] = []
    data = bytearray()
    prev = 0
    for value in values:
        current = int(round(value))
        delta = current - prev
        prev = current
        if delta == 0:
            flags.append(same_bit)
        elif 1 <= delta <= 255:
            flags.append(short_bit | same_bit)
            data.append(delta)
        elif -255 <= delta <= -1:
            flags.append(short_bit)
            data.append(-delta)
        else:
            flags.append(0)
            data += struct.pack(">h", delta)
    return flags, bytes(data)


def build_glyph(glyph: Glyph) -> bytes:
    """把中性表示序列化成简单字形的 ``glyf`` 表内容。

    提示指令（instructions）不写入——本项目会剥掉 ``fpgm``/``prep``/``cvt ``，
    留着旧指令既无用又会误导光栅化器。
    """
    contours = [c for c in glyph.contours if c.points]
    if not contours:
        return b""

    all_points = [p for c in contours for p in c.points]
    xs = [p.x for p in all_points]
    ys = [p.y for p in all_points]
    x_min = int(round(min(xs)))
    y_min = int(round(min(ys)))
    x_max = int(round(max(xs)))
    y_max = int(round(max(ys)))

    # 每点的 ON_CURVE 位
    base_flags = [_ON_CURVE if p.on else 0 for p in all_points]
    x_flags, x_data = _encode_deltas(xs, _X_SHORT, _X_SAME)
    y_flags, y_data = _encode_deltas(ys, _Y_SHORT, _Y_SAME)
    flags = [base_flags[i] | x_flags[i] | y_flags[i] for i in range(len(all_points))]

    # 带 REPEAT 压缩的 flag 流
    flag_stream = bytearray()
    i = 0
    n = len(flags)
    while i < n:
        f = flags[i]
        run = 1
        while i + run < n and flags[i + run] == f and run < 256:
            run += 1
        if run > 1:
            flag_stream.append(f | _REPEAT)
            flag_stream.append(run - 1)
        else:
            flag_stream.append(f)
        i += run

    end_pts: List[int] = []
    acc = -1
    for c in contours:
        acc += len(c.points)
        end_pts.append(acc)

    out = bytearray()
    out += struct.pack(">hhhhh", len(contours), x_min, y_min, x_max, y_max)
    out += struct.pack(f">{len(end_pts)}H", *end_pts)
    out += struct.pack(">H", 0)  # instructionLength = 0
    out += flag_stream
    out += x_data
    out += y_data
    return bytes(out)


def serialize_glyph(glyph_data: GlyphData) -> bytes:
    """把 :class:`GlyphData` 重新序列化（复合字形按原样重建）。"""
    if glyph_data.is_composite:
        return _serialize_composite(glyph_data)
    if glyph_data.glyph is None:
        return b""
    return build_glyph(glyph_data.glyph)


def _serialize_composite(glyph_data: GlyphData) -> bytes:
    components = glyph_data.components
    if not components:
        return b""
    out = bytearray()
    out += struct.pack(">hhhhh", -1, glyph_data.x_min, glyph_data.y_min,
                       glyph_data.x_max, glyph_data.y_max)
    for idx, comp in enumerate(components):
        flags = comp.flags
        if idx < len(components) - 1:
            flags |= _MORE_COMPONENTS
        if flags & _WE_HAVE_A_SCALE:
            flags &= ~_WE_HAVE_AN_X_AND_Y_SCALE
            flags &= ~_WE_HAVE_A_TWO_BY_TWO
        elif flags & _WE_HAVE_AN_X_AND_Y_SCALE:
            flags &= ~_WE_HAVE_A_TWO_BY_TWO
        elif flags & _WE_HAVE_A_TWO_BY_TWO:
            pass
        else:
            flags &= ~(_WE_HAVE_A_SCALE | _WE_HAVE_AN_X_AND_Y_SCALE | _WE_HAVE_A_TWO_BY_TWO)

        out += struct.pack(">HH", flags, comp.glyph_index)
        if flags & _ARG_1_AND_2_ARE_WORDS:
            out += struct.pack(">hh", comp.arg1, comp.arg2)
        else:
            out += struct.pack(">bb", _clamp_i8(comp.arg1), _clamp_i8(comp.arg2))

        if flags & _WE_HAVE_A_SCALE:
            s = _to_f2dot14(comp.scale[0])
            out += struct.pack(">h", s)
        elif flags & _WE_HAVE_AN_X_AND_Y_SCALE:
            out += struct.pack(">hh", _to_f2dot14(comp.scale[0]), _to_f2dot14(comp.scale[1]))
        elif flags & _WE_HAVE_A_TWO_BY_TWO:
            out += struct.pack(
                ">hhhh",
                _to_f2dot14(comp.scale[0]),
                _to_f2dot14(comp.scale[1]),
                _to_f2dot14(comp.scale[2]),
                _to_f2dot14(comp.scale[3]),
            )

    if components[-1].flags & _WE_HAVE_INSTRUCTIONS:
        instr = glyph_data.instructions
        out += struct.pack(">H", len(instr))
        out += instr
    return bytes(out)


def _clamp_i8(value: int) -> int:
    return max(-128, min(127, int(value)))


def _to_f2dot14(value: float) -> int:
    scaled = int(round(value * 16384.0))
    return max(-32768, min(32767, scaled))
