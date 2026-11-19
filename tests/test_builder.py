"""构建器（生成粗体 face）的测试。"""

from __future__ import annotations

import struct

import pytest

from boldgen.builder import (
    STRIPPED_TABLES,
    BuildOptions,
    UnsupportedFontError,
    build_bold,
)
from boldgen.sfnt import Font, write_sfnt
from boldgen.verify import ink_ratio, verify_font


def test_build_bold_writes_a_file(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    result = build_bold(square_font, str(out))
    assert out.exists()
    assert result.output == str(out)
    assert result.num_glyphs == 2  # .notdef + SQUARE
    assert result.family == "TestFamily"
    assert result.postscript_name == "TestFamily-Regular-Bold"


def test_build_bold_updates_metadata(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    font = Font(out.read_bytes())

    head = font.table_bytes("head")
    mac_style = struct.unpack_from(">H", head, 44)[0]
    assert mac_style & 0x0001
    assert struct.unpack_from(">h", head, 50)[0] == 1  # indexToLocFormat = long

    os2 = font.table_bytes("OS/2")
    assert struct.unpack_from(">H", os2, 4)[0] == 700
    fs_selection = struct.unpack_from(">H", os2, 62)[0]
    assert fs_selection & 0x0020
    assert not fs_selection & 0x0040
    assert os2[34] == 8  # PANOSE Weight = Bold


def test_build_bold_renames_style(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    font = Font(out.read_bytes())
    subfamilies = [r.text for r in font.names() if r.name_id == 2]
    assert subfamilies
    assert all(text == "Bold" for text in subfamilies)


def test_build_bold_strips_hinting_tables(tmp_path, strippable_font):
    out = tmp_path / "Strippable-Bold.ttf"
    build_bold(strippable_font, str(out))
    font = Font(out.read_bytes())
    for tag in STRIPPED_TABLES:
        assert not font.has_table(tag), tag


def test_build_bold_can_keep_hinting(tmp_path, strippable_font):
    out = tmp_path / "Strippable-Bold.ttf"
    build_bold(strippable_font, str(out), options=BuildOptions(strip_hint=False))
    font = Font(out.read_bytes())
    assert font.has_table("fpgm")


def test_build_bold_inserts_modification_notice(tmp_path, square_font):
    """修改声明写进 nameID 5（版本字符串）——某些字体的授权要求这一点。"""
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    font = Font(out.read_bytes())
    versions = [r.text for r in font.names() if r.name_id == 5]
    assert versions
    assert any("boldgen" in text for text in versions)


def test_build_bold_actually_grows_glyphs(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    ratio = ink_ratio(str(out), square_font)
    assert ratio is not None
    assert ratio > 1.0


def test_verify_font_accepts_generated_output(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    result = verify_font(str(out), source_path=square_font)
    assert result.ok, result.errors
    assert result.errors == []
    assert result.info["weight"] == 700
    assert result.info["macStyle"] & 0x0001


def test_verify_font_reports_non_bold_weight(tmp_path, square_font):
    """把 OS/2 字重改回 400 后，自检必须报错（而不是默默通过）。"""
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out))
    font = Font(out.read_bytes())
    tables = {tag: font.table_bytes(tag) for tag in font.tables}
    os2 = bytearray(tables["OS/2"])
    struct.pack_into(">H", os2, 4, 400)
    tables["OS/2"] = bytes(os2)
    broken = tmp_path / "Broken-Bold.ttf"
    broken.write_bytes(write_sfnt(tables))

    result = verify_font(str(broken))
    assert not result.ok
    assert any("usWeightClass" in message for message in result.errors)


def test_build_bold_rejects_non_truetype(tmp_path):
    bogus = tmp_path / "Bogus.ttf"
    bogus.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 64)
    with pytest.raises(UnsupportedFontError):
        build_bold(str(bogus), str(tmp_path / "out.ttf"))


def test_build_options_radius(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    result = build_bold(
        square_font, str(out), options=BuildOptions(strength=0.02)
    )
    assert result.radius == 20  # round(1000 * 0.02)


def test_build_bold_custom_weight(tmp_path, square_font):
    out = tmp_path / "Square-Bold.ttf"
    build_bold(square_font, str(out), options=BuildOptions(weight=800))
    font = Font(out.read_bytes())
    assert struct.unpack_from(">H", font.table_bytes("OS/2"), 4)[0] == 800
