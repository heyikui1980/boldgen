"""中文字体识别的测试。"""

from __future__ import annotations

import pytest

from boldgen.cjk import (
    CJK_SAMPLE_CODEPOINTS,
    cjk_family_names,
    has_cjk_char,
    is_cjk_face,
    is_cjk_name,
)


@pytest.mark.parametrize(
    "text",
    ["宋体", "黑体", "楷体", "仿宋", "文泉驿正黑", "MS 明朝", "游ゴシック"],
)
def test_has_cjk_char_true(text):
    assert has_cjk_char(text)


@pytest.mark.parametrize("text", ["SimSun", "DejaVu Sans", "Liberation Serif", ""])
def test_has_cjk_char_false(text):
    assert not has_cjk_char(text)


def test_is_cjk_name():
    assert is_cjk_name("SimSun", "宋体")
    assert not is_cjk_name("SimSun", "DejaVu Sans")
    assert not is_cjk_name()


def test_is_cjk_face():
    # 覆盖汉字 → 是中文字体
    assert is_cjk_face(True, "Foo")
    # 名字里有中文 → 是中文字体
    assert is_cjk_face(False, "宋体")
    # 两者都没有 → 不是
    assert not is_cjk_face(False, "Foo")


def test_cjk_family_names():
    assert cjk_family_names(["SimSun", "宋体", "NSimSun"]) == ["宋体"]


def test_sample_codepoints_are_han():
    for code in CJK_SAMPLE_CODEPOINTS:
        assert 0x4E00 <= code <= 0x9FFF
