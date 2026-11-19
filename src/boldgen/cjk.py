"""中文字体的识别。

两条判据（任一命中即视为"中文字体"）：

1. 字体覆盖了 CJK 统一表意文字区（U+4E00–U+9FA5 起的常用汉字）；
2. 家族名里含有中日韩文字。

第 1 条由 fontconfig 的 ``:charset=`` 查询直接给出，第 2 条由本模块判断。
"""

from __future__ import annotations

from typing import Iterable

__all__ = [
    "CJK_NAME_RANGES",
    "CJK_SAMPLE_CODEPOINTS",
    "has_cjk_char",
    "is_cjk_name",
    "is_cjk_face",
]

#: 判定"名字里有中日韩文字"的字符区间。
CJK_NAME_RANGES = (
    (0x2E80, 0x2EFF),  # CJK 部首补充
    (0x3000, 0x303F),  # CJK 标点
    (0x3040, 0x30FF),  # 假名
    (0x3100, 0x312F),  # 注音
    (0x3130, 0x318F),  # 谚文兼容字母
    (0x3400, 0x4DBF),  # CJK 扩展 A
    (0x4E00, 0x9FFF),  # CJK 统一表意文字
    (0xA960, 0xA97F),  # 谚文扩展 A
    (0xAC00, 0xD7AF),  # 谚文音节
    (0xF900, 0xFAFF),  # CJK 兼容表意文字
    (0xFF00, 0xFFEF),  # 全角字符
)

#: 用来查询 fontconfig charset 的样例码位。
CJK_SAMPLE_CODEPOINTS = (0x4E00, 0x9FA5)


def has_cjk_char(text: str) -> bool:
    """文本里是否含有中日韩文字。"""
    for ch in text:
        code = ord(ch)
        for low, high in CJK_NAME_RANGES:
            if low <= code <= high:
                return True
    return False


def is_cjk_name(*names: str) -> bool:
    """任一名字里有中日韩文字即返回 True。"""
    return any(has_cjk_char(name) for name in names if name)


def is_cjk_face(covers_han: bool, *names: str) -> bool:
    """综合判断一个 face 是否算"中文字体"。"""
    return bool(covers_han) or is_cjk_name(*names)


def cjk_family_names(names: Iterable[str]) -> list:
    """挑出名字里含中日韩文字的那几个。"""
    return [name for name in names if has_cjk_char(name)]
