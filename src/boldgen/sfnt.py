"""sfnt（TrueType/OpenType 容器）读写。

只依赖标准库。负责：

* 解析表目录（含 TrueType Collection / TTC 的多 face 支持）；
* 读写 ``name`` 表（按平台正确编码，支持本地化样式名）；
* 计算表校验和与 ``head.checkSumAdjustment``；
* 重新打包成 sfnt 文件。
"""

from __future__ import annotations

import struct
from typing import Dict, List, Optional, Tuple

__all__ = [
    "Font",
    "NameRecord",
    "read_name_table",
    "build_name_table",
    "table_checksum",
    "write_sfnt",
    "sfnt_version",
    "MAC_ROMAN",
]

#: 字体文件魔数 ``0x00010000``（TrueType outlines）。
sfnt_version = 0x00010000

#: TrueType Collection 魔数。
_TTC_MAGIC = b"ttcf"

#: ``head.checkSumAdjustment`` 的固定值。
_CHECKSUM_MAGIC = 0xB1B0AFBA

#: 平台 ID。
PLATFORM_UNICODE = 0
PLATFORM_MACINTOSH = 1
PLATFORM_ISO = 2
PLATFORM_MICROSOFT = 3

#: 常用语言 ID。
LANG_EN_US = 0x0409
LANG_ZH_CN = 0x0804
LANG_ZH_TW = 0x0404

#: nameID 含义（只列出本项目关心的）。
NAME_FAMILY = 1
NAME_SUBFAMILY = 2
NAME_UNIQUE_ID = 3
NAME_FULL_NAME = 4
NAME_VERSION = 5
NAME_POSTSCRIPT = 6
NAME_TYPO_FAMILY = 16
NAME_TYPO_SUBFAMILY = 17

#: MacRoman 编码表（TrueType name 表的 Macintosh 平台用它）。
MAC_ROMAN = "mac_roman"


# --------------------------------------------------------------------------
# 校验和
# --------------------------------------------------------------------------

def table_checksum(data: bytes) -> int:
    """计算一张表的校验和。

    规则：把数据按 4 字节大端整数求和（末尾不足 4 字节补零），模 2**32。
    """
    if len(data) % 4:
        data = data + b"\x00" * (4 - len(data) % 4)
    total = 0
    for (value,) in struct.iter_unpack(">I", data):
        total += value
    return total & 0xFFFFFFFF


# --------------------------------------------------------------------------
# 字体读取
# --------------------------------------------------------------------------

class Font:
    """一个 sfnt face 的只读视图。

    Args:
        data: 整个文件的内容。
        face_index: TTC 中的 face 序号（非 TTC 时必须为 0）。
    """

    def __init__(self, data: bytes, face_index: int = 0):
        self.data = data
        self.is_collection = data[:4] == _TTC_MAGIC
        self.face_index = face_index

        if self.is_collection:
            if len(data) < 12:
                raise ValueError("TTC 文件过短")
            num_fonts = struct.unpack_from(">I", data, 8)[0]
            if not 0 <= face_index < num_fonts:
                raise ValueError(
                    f"TTC face 序号越界：请求 {face_index}，文件共 {num_fonts} 个 face"
                )
            self.face_offset = struct.unpack_from(">I", data, 12 + 4 * face_index)[0]
            self.num_fonts = num_fonts
        else:
            if face_index != 0:
                raise ValueError("非 TTC 文件只能取 face 0")
            self.face_offset = 0
            self.num_fonts = 1

        self.tables: Dict[str, Tuple[int, int]] = {}
        #: 表目录里记录的校验和（tag → checkSum）。
        self.table_checksums: Dict[str, int] = {}
        self._parse_directory()

    def _parse_directory(self) -> None:
        off = self.face_offset
        if len(self.data) < off + 12:
            raise ValueError("字体文件过短，无法读取表目录")
        num_tables = struct.unpack_from(">H", self.data, off + 4)[0]
        pos = off + 12
        for _ in range(num_tables):
            tag, checksum, toff, tlen = struct.unpack_from(">4sIII", self.data, pos)
            pos += 16
            key = tag.decode("latin-1")
            if key not in self.tables:
                self.tables[key] = (toff, tlen)
                self.table_checksums[key] = checksum

    # -- 表访问 ---------------------------------------------------------

    def has_table(self, tag: str) -> bool:
        return tag in self.tables

    def table(self, tag: str) -> Optional[bytes]:
        """返回表内容；不存在返回 None。"""
        entry = self.tables.get(tag)
        if entry is None:
            return None
        offset, length = entry
        return self.data[offset : offset + length]

    def table_bytes(self, tag: str, default: bytes = b"") -> bytes:
        value = self.table(tag)
        return default if value is None else value

    # -- 常用字段 -------------------------------------------------------

    @property
    def units_per_em(self) -> int:
        head = self.table("head")
        if head is None or len(head) < 20:
            return 1000
        return struct.unpack_from(">H", head, 18)[0]

    @property
    def num_glyphs(self) -> int:
        maxp = self.table("maxp")
        if maxp is None or len(maxp) < 6:
            return 0
        return struct.unpack_from(">H", maxp, 4)[0]

    @property
    def num_tables(self) -> int:
        return len(self.tables)

    def names(self) -> List["NameRecord"]:
        """解析 name 表。"""
        return read_name_table(self.table_bytes("name"))


# --------------------------------------------------------------------------
# name 表
# --------------------------------------------------------------------------

class NameRecord:
    """name 表中的一条记录。"""

    __slots__ = ("platform_id", "encoding_id", "language_id", "name_id", "text")

    def __init__(
        self,
        platform_id: int,
        encoding_id: int,
        language_id: int,
        name_id: int,
        text: str,
    ):
        self.platform_id = platform_id
        self.encoding_id = encoding_id
        self.language_id = language_id
        self.name_id = name_id
        self.text = text

    @property
    def key(self) -> Tuple[int, int, int, int]:
        return (self.platform_id, self.encoding_id, self.language_id, self.name_id)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"NameRecord(pid={self.platform_id}, eid={self.encoding_id}, "
            f"lid=0x{self.language_id:04X}, nid={self.name_id}, text={self.text!r})"
        )


def _decode(data: bytes, platform_id: int, encoding_id: int) -> str:
    """按平台解码 name 记录。"""
    if platform_id in (PLATFORM_UNICODE, PLATFORM_MICROSOFT):
        try:
            return data.decode("utf-16-be")
        except UnicodeDecodeError:
            return data.decode("utf-16-be", errors="replace")
    if platform_id == PLATFORM_MACINTOSH:
        if encoding_id == 0:
            try:
                return data.decode(MAC_ROMAN)
            except UnicodeDecodeError:
                return data.decode(MAC_ROMAN, errors="replace")
        return data.decode("latin-1", errors="replace")
    return data.decode("latin-1", errors="replace")


def _encode(text: str, platform_id: int, encoding_id: int) -> bytes:
    """按平台编码 name 记录。

    * Unicode / Microsoft 平台 → UTF-16BE（中文名的正确编码）；
    * Macintosh 平台 → MacRoman（MacRoman 无法表示 CJK，会退化为 '?'）；
    * 其余（ISO 等）→ Latin-1，同样无法表示 CJK。
    """
    if platform_id in (PLATFORM_UNICODE, PLATFORM_MICROSOFT):
        return text.encode("utf-16-be")
    if platform_id == PLATFORM_MACINTOSH:
        if encoding_id == 0:
            return text.encode(MAC_ROMAN, errors="replace")
        return text.encode("latin-1", errors="replace")
    return text.encode("latin-1", errors="replace")


def ascii_fold(text: str) -> str:
    """把文本折叠成 ASCII（用于 PostScript 名等必须是 ASCII 的场合）。

    只保留 PostScript 名字允许的字符 ``A-Z a-z 0-9 . _ -``，
    其余一律换成 ``-``（含空格与标点——它们虽然可打印，但出现在
    PostScript 名里会让 fontconfig / FreeType 的匹配变脆）。
    """
    out = []
    for ch in text:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            out.append(ch)
        elif ch in "._-":
            out.append(ch)
        else:
            out.append("-")
    folded = "".join(out).strip("-")
    while "--" in folded:
        folded = folded.replace("--", "-")
    return folded


def read_name_table(raw: bytes) -> List[NameRecord]:
    """解析 name 表，返回记录列表。

    支持 format 0 与 format 1（format 1 的 language-tag 记录被忽略，
    因为本项目不需要语言标签）。
    """
    if len(raw) < 6:
        return []
    fmt, count, string_offset = struct.unpack_from(">HHH", raw, 0)
    if fmt not in (0, 1):
        return []
    records: List[NameRecord] = []
    for i in range(count):
        pos = 6 + 12 * i
        if pos + 12 > len(raw):
            break
        pid, eid, lid, nid, length, offset = struct.unpack_from(">HHHHHH", raw, pos)
        start = string_offset + offset
        chunk = raw[start : start + length]
        records.append(NameRecord(pid, eid, lid, nid, _decode(chunk, pid, eid)))
    return records


def _family_by_language(records: List[NameRecord]) -> Dict[int, str]:
    """按 languageID 索引 family 名（nameID 1，其次 nameID 16）。"""
    out: Dict[int, str] = {}
    for nid in (NAME_FAMILY, NAME_TYPO_FAMILY):
        for rec in records:
            if rec.name_id == nid and rec.text.strip():
                out.setdefault(rec.language_id, rec.text)
    return out


def _best_family(records: List[NameRecord]) -> str:
    """挑一个"最像英文名"的 family，用于 PostScript 名等场景。"""
    families = [r.text for r in records if r.name_id == NAME_FAMILY and r.text.strip()]
    if not families:
        families = [r.text for r in records if r.name_id == NAME_TYPO_FAMILY and r.text.strip()]
    if not families:
        return "Untitled"
    for text in families:
        if all(ord(ch) < 128 for ch in text):
            return text
    return families[0]


def build_name_table(
    records: List[NameRecord],
    *,
    style: str = "Bold",
    postscript_name: Optional[str] = None,
    localized_style: Optional[Dict[int, str]] = None,
    modification_note: Optional[str] = None,
) -> bytes:
    """基于原有记录生成新的 name 表。

    改动范围：

    * nameID 2（Subfamily）  → ``style``；
    * nameID 3（Unique ID）  → ``"<family>:<style>"``；
    * nameID 4（Full name）  → ``"<family> <style>"``；
    * nameID 6（PostScript） → ``postscript_name``；
    * nameID 17（Typographic Subfamily）→ ``style``。

    其余记录原样保留（按各自平台重新编码）。

    Args:
        localized_style: 可选的 ``{languageID: 本地化样式名}``。
            **默认不使用**——nameID 2 是 fontconfig 与绝大多数应用判断
            "这是粗体"的依据，写成"粗体"会破坏匹配。Windows/macOS 上的
            真实字体也一律使用英文样式名。
        modification_note: 可选的修改声明，会追加到 nameID 5（Version string）。
            某些字体的授权（例如 Arphic Public License）要求"在每个修改过的
            文件里插入显著的修改声明"，nameID 5 是 TrueType 里唯一合适的落点。
    """
    fam_by_lang = _family_by_language(records)
    base_family = _best_family(records)

    if postscript_name is None:
        postscript_name = f"{ascii_fold(base_family)}-{ascii_fold(style)}"
    postscript_name = ascii_fold(postscript_name)[:63]

    def style_for(language_id: int) -> str:
        if localized_style:
            return localized_style.get(language_id, style)
        return style

    new_records: List[NameRecord] = []
    seen: set = set()

    for rec in records:
        if rec.name_id == NAME_SUBFAMILY:
            text = style_for(rec.language_id)
        elif rec.name_id == NAME_UNIQUE_ID:
            fam = fam_by_lang.get(rec.language_id, base_family)
            text = f"{fam}:{style_for(rec.language_id)}"
        elif rec.name_id == NAME_FULL_NAME:
            fam = fam_by_lang.get(rec.language_id, base_family)
            text = f"{fam} {style_for(rec.language_id)}"
        elif rec.name_id == NAME_POSTSCRIPT:
            text = postscript_name
        elif rec.name_id == NAME_TYPO_SUBFAMILY:
            text = style_for(rec.language_id)
        elif rec.name_id == NAME_VERSION and modification_note:
            text = f"{rec.text}; {modification_note}" if rec.text else modification_note
        else:
            text = rec.text

        new = NameRecord(rec.platform_id, rec.encoding_id, rec.language_id, rec.name_id, text)
        if new.key in seen:
            continue
        seen.add(new.key)
        new_records.append(new)

    # 补齐缺失的关键记录
    def ensure(name_id: int, factory, platforms=((PLATFORM_MICROSOFT, 1, 0x0409),
                                                 (PLATFORM_MICROSOFT, 3, 0x0409))):
        for pid, eid, lid in platforms:
            key = (pid, eid, lid, name_id)
            if key in seen:
                continue
            seen.add(key)
            new_records.append(NameRecord(pid, eid, lid, name_id, factory(lid)))

    ensure(NAME_SUBFAMILY, lambda lid: style)
    ensure(NAME_FULL_NAME, lambda lid: f"{base_family} {style}")
    ensure(NAME_UNIQUE_ID, lambda lid: f"{base_family}:{style}")
    ensure(NAME_POSTSCRIPT, lambda lid: postscript_name)

    new_records.sort(key=lambda r: (r.platform_id, r.encoding_id, r.language_id, r.name_id))
    return _pack_name_table(new_records)


def _pack_name_table(records: List[NameRecord]) -> bytes:
    """把记录打包成 format 0 的 name 表。"""
    count = len(records)
    string_offset = 6 + 12 * count
    storage = bytearray()
    entries = bytearray()
    for rec in records:
        blob = _encode(rec.text, rec.platform_id, rec.encoding_id)
        entries += struct.pack(
            ">HHHHHH",
            rec.platform_id,
            rec.encoding_id,
            rec.language_id,
            rec.name_id,
            len(blob),
            len(storage),
        )
        storage += blob
    header = struct.pack(">HHH", 0, count, string_offset)
    return bytes(header + entries + storage)


# --------------------------------------------------------------------------
# 写文件
# --------------------------------------------------------------------------

def write_sfnt(tables: Dict[str, bytes], version: int = sfnt_version) -> bytes:
    """把表字典打包成 sfnt 文件，并填好校验和。

    * 每张表的 ``checkSum`` 按 OpenType 规范计算；
    * ``head.checkSumAdjustment`` 按规范计算（先置 0，再写回 0xB1B0AFBA - 全文校验和）。
    """
    tags = sorted(tables)
    num_tables = len(tags)
    if num_tables == 0:
        raise ValueError("没有表可写")

    # 表数据区
    header_size = 12 + 16 * num_tables
    data = bytearray()
    data_start = header_size
    directory = bytearray()
    offsets = {}
    for tag in tags:
        blob = tables[tag]
        offsets[tag] = data_start + len(data)
        data += blob
        pad = (-len(blob)) % 4
        data += b"\x00" * pad

    # searchRange / entrySelector / rangeShift
    entry_selector = max(0, (num_tables.bit_length() - 1))
    search_range = (2 ** entry_selector) * 16
    range_shift = num_tables * 16 - search_range

    out = bytearray()
    out += struct.pack(">IHHHH", version, num_tables, search_range, entry_selector, range_shift)
    for tag in tags:
        blob = tables[tag]
        if tag == "head":
            # 规范要求 head 表的目录校验和按 checkSumAdjustment = 0 计算
            # （该字段随后会被填上真实值），实际字体也都是这么做的。
            probe = bytearray(blob)
            if len(probe) >= 12:
                probe[8:12] = b"\x00\x00\x00\x00"
            checksum = table_checksum(bytes(probe))
        else:
            checksum = table_checksum(blob)
        out += struct.pack(
            ">4sIII",
            tag.encode("latin-1"),
            checksum,
            offsets[tag],
            len(blob),
        )
    out += data

    # head.checkSumAdjustment
    if "head" in offsets:
        head_off = offsets["head"]
        out[head_off + 8 : head_off + 12] = b"\x00\x00\x00\x00"
        adjustment = (_CHECKSUM_MAGIC - table_checksum(bytes(out))) & 0xFFFFFFFF
        out[head_off + 8 : head_off + 12] = struct.pack(">I", adjustment)

    return bytes(out)
