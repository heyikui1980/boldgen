"""构建合成粗体 face。

流程：

1. 读取源字体（支持 TTC 的指定 face）；
2. 把每个**简单字形**的轮廓向外偏移 ``r = round(upem * strength)``；
3. 复合字形原样保留（其分量字形各自加粗后自动继承效果）；
4. 更新 ``head`` / ``OS/2`` / ``name`` 表，剥掉不再适用的表；
5. 重新打包并计算校验和。
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import __version__, glyf as glyf_mod
from .geometry import Glyph, embolden
from .sfnt import (
    NAME_FAMILY,
    NAME_POSTSCRIPT,
    Font,
    ascii_fold,
    build_name_table,
    read_name_table,
    write_sfnt,
)

__all__ = [
    "BuildOptions",
    "BuildResult",
    "UnsupportedFontError",
    "build_bold",
    "STRIPPED_TABLES",
]

#: 会被剥掉的表：旧 hinting（会把加粗后的笔画又削细）、内嵌位图（未加粗的位图）、
#: 数字签名（改过字体后签名即失效）。
STRIPPED_TABLES = ("fpgm", "prep", "cvt ", "EBDT", "EBLC", "DSIG")

#: OS/2 fsSelection 位。
_FS_BOLD = 0x0020
_FS_REGULAR = 0x0040

#: head.macStyle 位。
_MACSTYLE_BOLD = 0x0001


class UnsupportedFontError(Exception):
    """字体格式不受支持（例如 CFF/OTF 轮廓）。"""


@dataclass
class BuildOptions:
    """构建参数。"""

    #: 加粗系数：外扩半径 = ``round(unitsPerEm * strength)``。
    strength: float = 0.015
    #: 写入 OS/2 的字重值。
    weight: int = 700
    #: 样式名后缀（用于 PostScript 名）。
    suffix: str = "Bold"
    #: 是否把隐含 on-curve 中点物化为显式点（几何更准，文件略大）。
    materialize: bool = True
    #: 斜接长度上限倍数，超过则退化为斜切。
    miter_limit: float = 4.0
    #: 是否剥掉 hinting / 位图 / 签名表。
    strip_hint: bool = True


@dataclass
class BuildResult:
    """构建结果。"""

    output: str
    num_glyphs: int = 0
    changed: int = 0
    radius: int = 0
    size: int = 0
    family: str = ""
    style: str = "Bold"
    postscript_name: str = ""
    source: str = ""
    face_index: int = 0
    warnings: List[str] = field(default_factory=list)


def _family_of(font: Font) -> str:
    for rec in font.names():
        if rec.name_id == NAME_FAMILY and rec.text.strip():
            return rec.text.strip()
    return os.path.splitext(os.path.basename(font.data[:0] or ""))[0] or "Untitled"


def _postscript_base(font: Font) -> str:
    """取源字体的 PostScript 名（没有就用 family 名）。"""
    for rec in font.names():
        if rec.name_id == NAME_POSTSCRIPT and rec.text.strip():
            return rec.text.strip()
    for rec in font.names():
        if rec.name_id == NAME_FAMILY and rec.text.strip():
            return rec.text.strip()
    return "Untitled"


def build_bold(
    src_path: str,
    out_path: str,
    face_index: int = 0,
    options: Optional[BuildOptions] = None,
) -> BuildResult:
    """从 ``src_path`` 生成粗体 face，写入 ``out_path``。

    Raises:
        UnsupportedFontError: 源字体没有 ``glyf`` 表（CFF/OTF 等）。
        ValueError: 字体结构异常。
    """
    options = options or BuildOptions()

    with open(src_path, "rb") as handle:
        data = handle.read()
    font = Font(data, face_index)

    if not font.has_table("glyf"):
        raise UnsupportedFontError(
            f"{src_path} 没有 glyf 表（可能是 CFF/OTF 轮廓）。"
            "本工具的内置引擎只处理 TrueType 轮廓；"
            "CFF 支持正在开发中，欢迎贡献。"
        )
    if not font.has_table("head") or not font.has_table("maxp"):
        raise ValueError(f"{src_path} 缺少 head/maxp 表，不是有效的 TrueType 字体")

    head = font.table_bytes("head")
    maxp = font.table_bytes("maxp")
    units_per_em = struct.unpack_from(">H", head, 18)[0] or 1000
    index_to_loc_format = struct.unpack_from(">h", head, 50)[0]
    num_glyphs = struct.unpack_from(">H", maxp, 4)[0]

    radius = max(1, int(round(units_per_em * options.strength)))
    style = options.suffix

    # --- glyf / loca ---
    glyf_raw = font.table_bytes("glyf")
    loca_offsets = glyf_mod.parse_loca(font.table_bytes("loca"), index_to_loc_format, num_glyphs)

    new_glyphs: List[bytes] = []
    changed = 0
    for gid in range(num_glyphs):
        start = loca_offsets[gid]
        end = loca_offsets[gid + 1] if gid + 1 < len(loca_offsets) else len(glyf_raw)
        length = max(0, end - start)
        parsed = glyf_mod.parse_glyph(glyf_raw, start, length)
        if parsed is None:
            new_glyphs.append(b"")
            continue
        if parsed.is_composite or parsed.glyph is None:
            # 复合字形原样保留
            new_glyphs.append(parsed.raw)
            continue
        bolded = embolden(
            parsed.glyph, radius, miter_limit=options.miter_limit,
            materialize=options.materialize,
        )
        blob = glyf_mod.build_glyph(bolded)
        if blob != parsed.raw:
            changed += 1
        new_glyphs.append(blob)

    # 重建 glyf + loca（统一用 long 格式）
    glyf_out = bytearray()
    loca_out = bytearray()
    for blob in new_glyphs:
        loca_out += struct.pack(">I", len(glyf_out))
        glyf_out += blob
        pad = (-len(blob)) % 4
        glyf_out += b"\x00" * pad
    loca_out += struct.pack(">I", len(glyf_out))

    # --- head ---
    head_out = bytearray(head)
    struct.pack_into(">h", head_out, 50, 1)  # indexToLocFormat = long
    mac_style = struct.unpack_from(">H", head_out, 44)[0]
    struct.pack_into(">H", head_out, 44, mac_style | _MACSTYLE_BOLD)

    # --- OS/2 ---
    os2_out = bytearray(font.table_bytes("OS/2"))
    if len(os2_out) >= 64:
        struct.pack_into(">H", os2_out, 4, options.weight)
        # fsSelection 在 OS/2 v0 里同样位于偏移 62，不需要按版本区分
        fs_selection = struct.unpack_from(">H", os2_out, 62)[0]
        fs_selection = (fs_selection & ~_FS_REGULAR) | _FS_BOLD
        struct.pack_into(">H", os2_out, 62, fs_selection)
        # PANOSE[2] = Weight → Bold(8)
        os2_out[34] = 8

    # --- name ---
    name_records = read_name_table(font.table_bytes("name"))
    ps_base = ascii_fold(_postscript_base(font))
    postscript_name = f"{ps_base}-{ascii_fold(style)}" if ps_base else ascii_fold(style)
    # 某些字体的授权（例如 Arphic Public License）要求"在每个修改过的文件里
    # 插入显著的修改声明"。TrueType 里唯一合适的落点是 nameID 5（版本字符串）。
    modification_note = (
        f"Modified by boldgen {__version__}: synthetic bold, "
        f"glyph outlines dilated by {radius} font units "
        f"(strength {options.strength}, unitsPerEm {units_per_em})"
    )
    name_out = build_name_table(
        name_records,
        style=style,
        postscript_name=postscript_name,
        modification_note=modification_note,
    )

    # --- 组装 ---
    tables: Dict[str, bytes] = {}
    for tag, blob in font.tables.items():
        tables[tag] = font.table_bytes(tag)
    tables["head"] = bytes(head_out)
    tables["glyf"] = bytes(glyf_out)
    tables["loca"] = bytes(loca_out)
    tables["name"] = name_out
    if len(os2_out) >= 64:
        tables["OS/2"] = bytes(os2_out)

    if options.strip_hint:
        for tag in STRIPPED_TABLES:
            tables.pop(tag, None)

    # glyf/loca 变化后，其它表里的 checksum 会失效——write_sfnt 会统一重算。
    out = write_sfnt(tables)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(out)

    return BuildResult(
        output=out_path,
        num_glyphs=num_glyphs,
        changed=changed,
        radius=radius,
        size=len(out),
        family=_family_of(font),
        style=style,
        postscript_name=postscript_name,
        source=src_path,
        face_index=face_index,
    )
