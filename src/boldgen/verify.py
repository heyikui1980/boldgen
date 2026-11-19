"""产物自检。

不依赖任何第三方库：直接读回生成的字体文件，检查表结构、元数据、
每个字形能否解析、校验和是否正确，并可与源字体比较墨量。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import glyf as glyf_mod
from .geometry import contour_area, glyph_area
from .sfnt import Font, NAME_SUBFAMILY, table_checksum

__all__ = ["VerifyResult", "verify_font", "ink_area", "ink_ratio"]

#: ``head.checkSumAdjustment`` 的固定值。
_CHECKSUM_MAGIC = 0xB1B0AFBA

#: 合成的粗体墨量应当落在这个区间（相对常规字重的倍数）。
#:
#: 注意这是**控制多边形面积**的代理指标，数值与字形形状有关：
#: 实心方块这类"胖"字形只有 1.15 左右，笔画细密的中文汉字一般在 1.7–2.0
#: （本机实测 SimSun 为 1.85）。WPS 自己出 bug 时该值可达 2.3–10.2。
#: 因此这里取一个宽松的区间，只用于"明显不对劲"时报警；
#: 真正可靠的判据是"粗体墨量必须大于常规"（见 :func:`verify_font`）。
INK_RATIO_MIN = 1.02
INK_RATIO_MAX = 2.50


@dataclass
class VerifyResult:
    """自检结果。"""

    path: str
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def fail(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def ink_area(path: str, face_index: int = 0) -> Tuple[float, int]:
    """返回 (净墨量面积, 字形数)。

    净墨量 = 各轮廓**有符号**面积之和的绝对值。TrueType 里外轮廓顺时针
    （有符号面积为负）、内孔逆时针（为正），所以直接求和就等于"笔画面积
    减去孔洞面积"，取绝对值即为墨量。

    这是**墨量**的无依赖近似值：数值越大，字形越"胖"。
    """
    with open(path, "rb") as handle:
        data = handle.read()
    font = Font(data, face_index)
    if not font.has_table("glyf"):
        return (0.0, 0)
    head = font.table_bytes("head")
    maxp = font.table_bytes("maxp")
    ilf = struct.unpack_from(">h", head, 50)[0]
    num_glyphs = struct.unpack_from(">H", maxp, 4)[0]
    loca = glyf_mod.parse_loca(font.table_bytes("loca"), ilf, num_glyphs)
    glyf_raw = font.table_bytes("glyf")

    total = 0.0
    for gid in range(num_glyphs):
        start = loca[gid]
        end = loca[gid + 1] if gid + 1 < len(loca) else len(glyf_raw)
        parsed = glyf_mod.parse_glyph(glyf_raw, start, max(0, end - start))
        if parsed is None or parsed.glyph is None:
            continue
        for contour in parsed.glyph.contours:
            total += contour_area(contour)
    return (abs(total), num_glyphs)


def ink_ratio(
    bold_path: str,
    regular_path: str,
    face_index: int = 0,
    regular_face_index: Optional[int] = None,
) -> Optional[float]:
    """粗体与常规字体的墨量比。

    Args:
        bold_path: 粗体文件路径（通常是单 face 的 .ttf）。
        regular_path: 常规字体路径（可能是 .ttc）。
        face_index: 粗体文件里要测的 face 序号。
        regular_face_index: 常规字体里要测的 face 序号；默认与 ``face_index`` 相同。
            两者不同时（例如粗体是 face 0、常规是 TTC 的 face 1）必须显式指定。
    """
    if regular_face_index is None:
        regular_face_index = face_index
    bold, _ = ink_area(bold_path, face_index)
    regular, _ = ink_area(regular_path, regular_face_index)
    if regular <= 0:
        return None
    return bold / regular


def verify_font(
    path: str,
    face_index: int = 0,
    expect_stripped: bool = True,
    source_path: Optional[str] = None,
    source_face_index: Optional[int] = None,
) -> VerifyResult:
    """对生成的粗体文件做结构与元数据自检。

    Args:
        path: 待检查的字体文件。
        face_index: ``path`` 里要检查的 face 序号。生成的产物总是单 face 的
            .ttf，所以是 0。
        expect_stripped: 是否要求 hinting / 位图 / 签名表已被剥掉。
        source_path: 源字体路径（用来比对 cmap / hmtx 与墨量）。
        source_face_index: 源字体里的 face 序号。源是 .ttc 时必须显式指定，
            否则会用 ``face_index``（对 .ttc 的 face 1 来说那是错的）。
    """
    result = VerifyResult(path=path)
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        result.fail(f"无法读取：{exc}")
        return result

    try:
        font = Font(data, face_index)
    except ValueError as exc:
        result.fail(f"sfnt 结构解析失败：{exc}")
        return result

    # --- 必需表 ---
    for tag in ("head", "maxp", "hhea", "hmtx", "cmap", "name", "glyf", "loca", "post"):
        if not font.has_table(tag):
            result.fail(f"缺少必需表 {tag!r}")

    if not font.has_table("glyf"):
        return result

    # --- name ---
    subfamilies = [r.text for r in font.names() if r.name_id == NAME_SUBFAMILY]
    if not subfamilies:
        result.fail("name 表里没有 nameID 2（Subfamily）")
    elif not any("bold" in text.lower() for text in subfamilies):
        result.fail(f"nameID 2 里没有 'Bold'：{subfamilies}")
    result.info["subfamily"] = subfamilies

    # --- OS/2 ---
    os2 = font.table("OS/2")
    if os2 is None:
        result.fail("缺少 OS/2 表")
    elif len(os2) >= 64:
        weight = struct.unpack_from(">H", os2, 4)[0]
        fs_selection = struct.unpack_from(">H", os2, 62)[0]
        if weight < 600:
            result.fail(f"OS/2.usWeightClass = {weight}，不是粗体（应 >= 600）")
        if not fs_selection & 0x0020:
            result.fail("OS/2.fsSelection 的 BOLD 位没有置位")
        if fs_selection & 0x0040:
            result.fail("OS/2.fsSelection 的 REGULAR 位仍然置位")
        result.info["weight"] = weight
        result.info["fsSelection"] = fs_selection

    # --- head ---
    head = font.table_bytes("head")
    mac_style = struct.unpack_from(">H", head, 44)[0]
    if not mac_style & 0x0001:
        result.fail("head.macStyle 的 bold 位没有置位")
    result.info["macStyle"] = mac_style
    result.info["unitsPerEm"] = struct.unpack_from(">H", head, 18)[0]

    # --- 校验和 ---
    bad = []
    for tag, (offset, length) in font.tables.items():
        blob = data[offset : offset + length]
        if tag == "head":
            # head 的目录校验和按 checkSumAdjustment = 0 计算
            probe = bytearray(blob)
            if len(probe) >= 12:
                probe[8:12] = b"\x00\x00\x00\x00"
            blob = bytes(probe)
        stored = font.table_checksums.get(tag)
        if stored != table_checksum(blob):
            bad.append(tag)
    if bad:
        result.fail(f"表校验和不匹配：{', '.join(bad)}")

    # head.checkSumAdjustment
    head_offset = font.tables["head"][0]
    adjustment = struct.unpack_from(">I", data, head_offset + 8)[0]
    zeroed = bytearray(data)
    zeroed[head_offset + 8 : head_offset + 12] = b"\x00\x00\x00\x00"
    expected_adjustment = (_CHECKSUM_MAGIC - table_checksum(bytes(zeroed))) & 0xFFFFFFFF
    if adjustment != expected_adjustment:
        result.fail(
            f"head.checkSumAdjustment 不正确：{adjustment:#x}（应为 {expected_adjustment:#x}）"
        )

    # --- 被剥掉的表 ---
    if expect_stripped:
        from .builder import STRIPPED_TABLES

        present = [tag for tag in STRIPPED_TABLES if font.has_table(tag)]
        if present:
            result.fail(f"这些表应该被剥掉但仍在：{', '.join(present)}")

    # --- 每个字形都能解析 ---
    ilf = struct.unpack_from(">h", head, 50)[0]
    num_glyphs = struct.unpack_from(">H", font.table_bytes("maxp"), 4)[0]
    loca = glyf_mod.parse_loca(font.table_bytes("loca"), ilf, num_glyphs)
    glyf_raw = font.table_bytes("glyf")
    broken = []
    for gid in range(num_glyphs):
        start = loca[gid]
        end = loca[gid + 1] if gid + 1 < len(loca) else len(glyf_raw)
        parsed = glyf_mod.parse_glyph(glyf_raw, start, max(0, end - start))
        if parsed is None and end > start:
            broken.append(gid)
    if broken:
        result.fail(f"有 {len(broken)} 个字形无法解析（gid: {broken[:10]}）")
    result.info["num_glyphs"] = num_glyphs

    # --- 与源字体比较 ---
    if source_path:
        if source_face_index is None:
            source_face_index = face_index
        try:
            with open(source_path, "rb") as handle:
                src_data = handle.read()
            src = Font(src_data, source_face_index)
            for tag in ("cmap", "hmtx", "maxp"):
                if src.has_table(tag):
                    if not font.has_table(tag):
                        result.fail(f"源字体有 {tag} 表，产物却没有")
                    elif src.table_bytes(tag) != font.table_bytes(tag):
                        result.fail(f"{tag} 表与源字体不一致")
            if src.has_table("cmap") and font.has_table("cmap"):
                if src.table_bytes("cmap") != font.table_bytes("cmap"):
                    result.fail("cmap 表与源字体不一致（字符映射被改动）")
            ratio = ink_ratio(path, source_path, face_index, source_face_index)
            if ratio is not None:
                result.info["ink_ratio"] = ratio
                if ratio <= 1.0:
                    result.fail(
                        f"粗体墨量比常规还小（{ratio:.3f}）——加粗根本没生效"
                    )
                elif not (INK_RATIO_MIN <= ratio <= INK_RATIO_MAX):
                    result.warn(
                        f"墨量比 {ratio:.2f} 不在预期区间 "
                        f"{INK_RATIO_MIN}–{INK_RATIO_MAX}"
                    )
        except (OSError, ValueError) as exc:
            result.warn(f"无法与源字体比较：{exc}")

    return result
