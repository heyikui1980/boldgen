"""sfnt 容器与 name 表的测试。"""

from __future__ import annotations

import struct

import pytest

from boldgen.sfnt import (
    NAME_FAMILY,
    NAME_POSTSCRIPT,
    NAME_SUBFAMILY,
    Font,
    NameRecord,
    ascii_fold,
    build_name_table,
    read_name_table,
    table_checksum,
    write_sfnt,
)

from conftest import make_font_bytes


def test_table_checksum_pads_to_four_bytes():
    assert table_checksum(b"\x00\x00\x00\x00") == 0
    # 末尾补零后与显式补齐等价
    assert table_checksum(b"\x00\x01\x02") == table_checksum(b"\x00\x01\x02\x00")


def test_table_checksum_is_mod_2_32():
    data = b"\xff\xff\xff\xff" * 2
    assert table_checksum(data) == (0xFFFFFFFF * 2) & 0xFFFFFFFF


def test_ascii_fold():
    assert ascii_fold("SimSun") == "SimSun"
    assert ascii_fold("宋体") == ""
    assert ascii_fold("Fang Song!") == "Fang-Song"
    assert ascii_fold("A/B") == "A-B"
    assert ascii_fold("Noto Serif CJK SC") == "Noto-Serif-CJK-SC"
    assert ascii_fold("--x--") == "x"


def test_name_table_roundtrip():
    records = [
        NameRecord(3, 1, 0x0409, NAME_FAMILY, "SimSun"),
        NameRecord(3, 1, 0x0409, NAME_SUBFAMILY, "Regular"),
    ]
    blob = build_name_table(records, style="Bold", postscript_name="SimSun-Bold")
    parsed = read_name_table(blob)
    by_id = {(r.platform_id, r.language_id, r.name_id): r.text for r in parsed}
    assert by_id[(3, 0x0409, NAME_FAMILY)] == "SimSun"
    assert by_id[(3, 0x0409, NAME_SUBFAMILY)] == "Bold"
    assert by_id[(3, 0x0409, NAME_POSTSCRIPT)] == "SimSun-Bold"


def test_name_table_style_is_always_english_bold():
    """nameID 2 必须是英文 Bold——它是应用判断"这是粗体"的依据。"""
    records = [
        NameRecord(3, 1, 0x0804, NAME_FAMILY, "宋体"),
        NameRecord(3, 1, 0x0804, NAME_SUBFAMILY, "常规"),
    ]
    blob = build_name_table(records, style="Bold")
    parsed = read_name_table(blob)
    zh = [r.text for r in parsed if r.language_id == 0x0804 and r.name_id == NAME_SUBFAMILY]
    assert zh and all(text == "Bold" for text in zh)


def test_name_table_keeps_family_names_untouched():
    records = [NameRecord(3, 1, 0x0804, NAME_FAMILY, "宋体")]
    blob = build_name_table(records, style="Bold")
    parsed = read_name_table(blob)
    families = {r.text for r in parsed if r.name_id == NAME_FAMILY}
    assert "宋体" in families


def test_name_table_full_and_unique_id_are_rewritten():
    records = [
        NameRecord(3, 1, 0x0409, NAME_FAMILY, "SimSun"),
        NameRecord(3, 1, 0x0409, 3, "SimSun:Regular"),
        NameRecord(3, 1, 0x0409, 4, "SimSun Regular"),
    ]
    blob = build_name_table(records, style="Bold")
    parsed = read_name_table(blob)
    by_id = {r.name_id: r.text for r in parsed if r.language_id == 0x0409}
    assert by_id[3] == "SimSun:Bold"
    assert by_id[4] == "SimSun Bold"


def test_read_name_table_ignores_garbage():
    assert read_name_table(b"") == []
    assert read_name_table(b"\x00\x09") == []


def test_write_sfnt_produces_parsable_font():
    data = make_font_bytes([])
    font = Font(data)
    assert font.has_table("head")
    assert font.has_table("glyf")
    assert font.units_per_em == 1000


def test_write_sfnt_table_checksums_are_correct():
    data = make_font_bytes([])
    font = Font(data)
    for tag, (offset, length) in font.tables.items():
        blob = data[offset : offset + length]
        if tag == "head":
            probe = bytearray(blob)
            probe[8:12] = b"\x00\x00\x00\x00"
            blob = bytes(probe)
        assert font.table_checksums[tag] == table_checksum(blob), tag


def test_head_checksum_adjustment():
    data = make_font_bytes([])
    font = Font(data)
    head_offset = font.tables["head"][0]
    adjustment = struct.unpack_from(">I", data, head_offset + 8)[0]
    zeroed = bytearray(data)
    zeroed[head_offset + 8 : head_offset + 12] = b"\x00\x00\x00\x00"
    expected = (0xB1B0AFBA - table_checksum(bytes(zeroed))) & 0xFFFFFFFF
    assert adjustment == expected


def test_font_rejects_face_index_out_of_range():
    data = make_font_bytes([])
    with pytest.raises(ValueError):
        Font(data, 3)


def test_font_rejects_garbage():
    with pytest.raises(ValueError):
        Font(b"\x00\x01\x02\x03")


def test_write_sfnt_requires_tables():
    with pytest.raises(ValueError):
        write_sfnt({})
