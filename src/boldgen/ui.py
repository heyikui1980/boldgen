"""交互式界面（纯标准库，无需 curses）。

流程：

1. **勾选列表** —— 从扫描结果里挑要处理的字体家族；
2. **单选模式** —— 合成粗体生成器 / fontconfig 别名；
3. **参数确认** —— 加粗强度、字重；别名模式下逐家族确认目标；
4. **计划预览** —— 将要写哪些文件、占多少磁盘，确认后执行。

按键（勾选列表）：

===========  ==========================================
``空格``      切换当前行
``j`` / ``k``  下移 / 上移
``a``        全选
``n``        全不选
``/``        按关键词过滤（回车应用，Esc 取消）
``Enter``    下一步
``q``        取消
===========  ==========================================

非 TTY 环境（管道、CI）下自动退化为"逐行输入"，不会挂起。
"""

from __future__ import annotations

import os
import sys
import termios
import tty
from typing import Callable, List, Optional, Sequence, Tuple

from .discover import FamilyInfo

__all__ = [
    "InteractionCancelled",
    "is_interactive",
    "select_families",
    "choose_mode",
    "confirm",
    "ask_number",
    "ask_text",
]


class InteractionCancelled(Exception):
    """用户按了 q 取消。"""


def is_interactive() -> bool:
    """当前环境是否支持交互。"""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _read_key() -> str:
    """读一个按键（raw 模式）。"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":  # ESC 序列
            # 读掉后续字节
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
            return "esc"
        return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _print_line(text: str = "", end: str = "\n") -> None:
    sys.stdout.write(text + end)
    sys.stdout.flush()


# --------------------------------------------------------------------------
# 勾选列表
# --------------------------------------------------------------------------

def select_families(
    families: Sequence[FamilyInfo],
    title: str = "选择要处理的字体家族",
    limit: int = 25,
) -> List[FamilyInfo]:
    """让用户勾选若干家族。

    Returns:
        选中的家族列表（保持扫描顺序）。
    """
    if not families:
        _print_line("没有可选的字体家族。")
        return []

    if not is_interactive():
        return _select_families_plain(families, title)

    selected = {info.key for info in families}
    keyword = ""
    cursor = 0

    def visible() -> List[FamilyInfo]:
        if not keyword:
            return list(families)
        low = keyword.lower()
        out = []
        for info in families:
            haystack = " ".join(info.names).lower()
            if low in haystack:
                out.append(info)
        return out

    while True:
        items = visible()
        if not items:
            _print_line(f"没有匹配 '{keyword}' 的家族，输入新的关键词或按 q 退出。")
            choice = _read_key()
            if choice in ("q", "\x03"):
                raise InteractionCancelled
            if choice == "/":
                keyword = ""
            continue
        cursor = max(0, min(cursor, len(items) - 1))

        _print_line()
        _print_line(f"── {title} " + "─" * max(0, 56 - len(title)))
        if keyword:
            _print_line(f"   过滤：{keyword}")
        _print_line(
            "   空格=勾选  j/k=移动  a=全选  n=全不选  /=过滤  Enter=下一步  q=取消"
            "   （a/n 不受过滤影响）"
        )
        _print_line()
        start = max(0, cursor - limit // 2)
        for pos, info in enumerate(items[start : start + limit], start=start):
            mark = "x" if info.key in selected else " "
            arrow = ">" if pos == cursor else " "
            flag = "有粗体" if info.has_real_bold else "缺粗体"
            _print_line(f" {arrow} [{mark}] {info.display_name:<34} {flag}")
        if len(items) > limit:
            _print_line(f"   …… 共 {len(items)} 项，当前显示 {limit} 项")
        _print_line()

        key = _read_key()
        if key in ("q", "\x03"):
            raise InteractionCancelled
        if key == " ":
            info = items[cursor]
            if info.key in selected:
                selected.discard(info.key)
            else:
                selected.add(info.key)
        elif key in ("j", "down"):
            cursor += 1
        elif key in ("k", "up"):
            cursor -= 1
        elif key == "a":
            # 全选针对**全部**家族，不受过滤影响——否则"全选"的含义会随过滤而变。
            selected.update(info.key for info in families)
        elif key == "n":
            for info in families:
                selected.discard(info.key)
        elif key == "/":
            _print_line("   输入关键词（直接回车清除）：", end="")
            sys.stdout.flush()
            keyword = sys.stdin.readline().strip()
            cursor = 0
        elif key in ("\r", "\n"):
            picked = [info for info in families if info.key in selected]
            if not picked:
                _print_line("   至少要选一个家族（按 q 取消）。")
                continue
            return picked


def _select_families_plain(
    families: Sequence[FamilyInfo], title: str
) -> List[FamilyInfo]:
    """非 TTY 环境下的降级方案：逐行输入序号。"""
    _print_line(f"—— {title} ——")
    for index, info in enumerate(families, 1):
        flag = "有粗体" if info.has_real_bold else "缺粗体"
        _print_line(f"  {index:3d}. {info.display_name:<34} {flag}")
    _print_line("输入要处理的序号（逗号分隔；'all' = 全部；直接回车 = 取消）：")
    try:
        line = sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt):
        return []
    if not line:
        return []
    if line.lower() == "all":
        return list(families)
    picked: List[FamilyInfo] = []
    for chunk in line.replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            index = int(chunk)
        except ValueError:
            continue
        if 1 <= index <= len(families):
            picked.append(families[index - 1])
    return picked


# --------------------------------------------------------------------------
# 单选
# --------------------------------------------------------------------------

MODE_GENERATE = "generate"
MODE_ALIAS = "alias"

_MODES = (
    (
        MODE_GENERATE,
        "合成粗体生成器",
        "离线生成真正的 Bold 字体文件，任何应用都能匹配到。效果最好，"
        "每个家族多占一份磁盘。",
    ),
    (
        MODE_ALIAS,
        "fontconfig 别名",
        "把加粗请求重定向到另一个已有粗体的家族。零额外磁盘占用，"
        "但字形会变成目标字体的。",
    ),
)


def choose_mode() -> str:
    """单选处理方式。"""
    if not is_interactive():
        _print_line("—— 选择处理方式 ——")
        for index, (_, title, desc) in enumerate(_MODES, 1):
            _print_line(f"  {index}. {title} —— {desc}")
        _print_line("输入序号（1 或 2）：")
        try:
            line = sys.stdin.readline().strip()
        except (EOFError, KeyboardInterrupt):
            line = "1"
        return MODE_ALIAS if line.strip() == "2" else MODE_GENERATE

    cursor = 0
    while True:
        _print_line()
        _print_line("── 选择处理方式 " + "─" * 40)
        for index, (_, title, desc) in enumerate(_MODES):
            arrow = ">" if index == cursor else " "
            radio = "(*)" if index == cursor else "( )"
            _print_line(f" {arrow} {radio} {title}")
            _print_line(f"       {desc}")
        _print_line()
        key = _read_key()
        if key in ("q", "\x03"):
            raise InteractionCancelled
        if key in ("j", "down"):
            cursor = (cursor + 1) % len(_MODES)
        elif key in ("k", "up"):
            cursor = (cursor - 1) % len(_MODES)
        elif key == " ":
            return _MODES[cursor][0]
        elif key in ("\r", "\n"):
            return _MODES[cursor][0]
        elif key in ("1", "2"):
            return _MODES[int(key) - 1][0]


# --------------------------------------------------------------------------
# 简单提问
# --------------------------------------------------------------------------

def confirm(prompt: str, default: bool = True) -> bool:
    """是/否提问。"""
    suffix = "[Y/n]" if default else "[y/N]"
    if not is_interactive():
        return default
    while True:
        _print_line(f"{prompt} {suffix}")
        key = _read_key()
        if key in ("y", "Y"):
            return True
        if key in ("n", "N"):
            return False
        if key in ("\r", "\n"):
            return default


def ask_number(
    prompt: str,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """问一个数值。"""
    if not is_interactive():
        return default
    _print_line(f"{prompt}（默认 {default}）：")
    try:
        line = sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt):
        return default
    if not line:
        return default
    try:
        value = float(line)
    except ValueError:
        _print_line("   不是一个数字，用默认值。")
        return default
    if minimum is not None and value < minimum:
        _print_line(f"   不能小于 {minimum}，用默认值。")
        return default
    if maximum is not None and value > maximum:
        _print_line(f"   不能大于 {maximum}，用默认值。")
        return default
    return value


def ask_text(prompt: str, default: str = "") -> str:
    """问一行文本。"""
    if not is_interactive():
        return default
    _print_line(f"{prompt}（默认 {default}）：")
    try:
        line = sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return line or default
