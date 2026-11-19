"""交互式界面（ui.py）的测试。

交互界面有两套路径：

* **非 TTY**（管道 / CI）——退化为逐行输入；
* **TTY**——raw 模式单键操作。

TTY 路径靠 monkeypatch ``_read_key`` 喂脚本化的按键序列来测，
不碰真终端。
"""

from __future__ import annotations

import io
import sys

import pytest

from boldgen import ui
from boldgen.discover import Face, FamilyInfo


def make_family(key: str, names=None, weight: int = 80) -> FamilyInfo:
    face = Face(
        path=f"/usr/share/fonts/{key}.ttf",
        index=0,
        family=key,
        families=list(names or [key]),
        style="Regular",
        styles=["Regular"],
        weight=weight,
        slant=0,
    )
    return FamilyInfo(
        key=key,
        names=list(names or [key]),
        faces=[face],
        is_cjk=True,
    )


@pytest.fixture
def families():
    return [
        make_family("SimSun", ["SimSun", "宋体"]),
        make_family("SimHei", ["SimHei", "黑体"]),
        make_family("KaiTi", ["KaiTi", "楷体"]),
    ]


@pytest.fixture
def plain(monkeypatch):
    """强制非 TTY 模式。"""
    monkeypatch.setattr(ui, "is_interactive", lambda: False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))


# --------------------------------------------------------------------------
# 非 TTY 路径
# --------------------------------------------------------------------------

def test_select_families_empty(families):
    assert ui.select_families([]) == []


def test_select_families_plain_by_index(families, plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("1,3\n"))
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimSun", "KaiTi"]


def test_select_families_plain_all(families, plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("all\n"))
    assert [f.key for f in ui.select_families(families)] == ["SimSun", "SimHei", "KaiTi"]


def test_select_families_plain_empty_line_cancels(families, plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    assert ui.select_families(families) == []


def test_select_families_plain_ignores_bad_index(families, plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("0,99,x,2\n"))
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimHei"]


def test_select_families_plain_accepts_fullwidth_comma(families, plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("1，3\n"))
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimSun", "KaiTi"]


def test_choose_mode_plain_generate(plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("1\n"))
    assert ui.choose_mode() == ui.MODE_GENERATE


def test_choose_mode_plain_alias(plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("2\n"))
    assert ui.choose_mode() == ui.MODE_ALIAS


def test_choose_mode_plain_defaults_to_generate(plain, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    assert ui.choose_mode() == ui.MODE_GENERATE


def test_confirm_plain_returns_default(plain):
    assert ui.confirm("继续？", default=True) is True
    assert ui.confirm("继续？", default=False) is False


def test_ask_number_plain_returns_default(plain):
    assert ui.ask_number("强度", 0.015) == 0.015


def test_ask_text_plain_returns_default(plain):
    assert ui.ask_text("名字", "abc") == "abc"


# --------------------------------------------------------------------------
# TTY 路径
# --------------------------------------------------------------------------

@pytest.fixture
def tty(monkeypatch):
    """强制 TTY 模式。"""
    monkeypatch.setattr(ui, "is_interactive", lambda: True)


def _script(monkeypatch, keys):
    """让 ``_read_key`` 依次返回给定的按键。"""
    queue = list(keys)
    monkeypatch.setattr(ui, "_read_key", lambda: queue.pop(0))


def test_select_families_tty_toggles_with_space(families, tty, monkeypatch):
    # 默认全选 → 空格取消第一项 → Enter 确认
    _script(monkeypatch, [" ", "\r"])
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimHei", "KaiTi"]


def test_select_families_tty_select_all(families, tty, monkeypatch):
    # 先全不选，再全选
    _script(monkeypatch, ["n", "a", "\r"])
    picked = ui.select_families(families)
    assert len(picked) == 3


def test_select_families_tty_moves_cursor(families, tty, monkeypatch):
    # 移动到第二项后取消勾选
    _script(monkeypatch, ["j", " ", "\r"])
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimSun", "KaiTi"]


def test_select_families_tty_q_cancels(families, tty, monkeypatch):
    _script(monkeypatch, ["q"])
    with pytest.raises(ui.InteractionCancelled):
        ui.select_families(families)


def test_select_families_tty_refuses_empty_selection(families, tty, monkeypatch):
    # 全不选 → Enter → 提示并继续 → 再全选 → Enter
    _script(monkeypatch, ["n", "\r", "a", "\r"])
    picked = ui.select_families(families)
    assert len(picked) == 3


def test_select_families_tty_filter(families, tty, monkeypatch):
    # "/" 之后从 stdin 读关键词；"n" 全不选，再空格勾选唯一可见的那一项
    monkeypatch.setattr(sys, "stdin", io.StringIO("KaiTi\n"))
    _script(monkeypatch, ["/", "n", " ", "\r"])
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["KaiTi"]


def test_select_families_tty_filter_keeps_hidden_selection(families, tty, monkeypatch):
    """过滤只影响显示，不影响已勾选状态。"""
    monkeypatch.setattr(sys, "stdin", io.StringIO("KaiTi\n"))
    _script(monkeypatch, ["/", "\r"])
    picked = ui.select_families(families)
    assert [f.key for f in picked] == ["SimSun", "SimHei", "KaiTi"]


def test_choose_mode_tty_space_confirms_current(families, tty, monkeypatch):
    _script(monkeypatch, [" "])
    assert ui.choose_mode() == ui.MODE_GENERATE


def test_choose_mode_tty_j_then_space(tty, monkeypatch):
    _script(monkeypatch, ["j", " "])
    assert ui.choose_mode() == ui.MODE_ALIAS


def test_choose_mode_tty_number_key(tty, monkeypatch):
    _script(monkeypatch, ["2"])
    assert ui.choose_mode() == ui.MODE_ALIAS


def test_choose_mode_tty_q_cancels(tty, monkeypatch):
    _script(monkeypatch, ["q"])
    with pytest.raises(ui.InteractionCancelled):
        ui.choose_mode()


def test_confirm_tty_yes(tty, monkeypatch):
    _script(monkeypatch, ["y"])
    assert ui.confirm("继续？") is True


def test_confirm_tty_no(tty, monkeypatch):
    _script(monkeypatch, ["n"])
    assert ui.confirm("继续？") is False


def test_confirm_tty_enter_uses_default(tty, monkeypatch):
    _script(monkeypatch, ["\r"])
    assert ui.confirm("继续？", default=True) is True
    _script(monkeypatch, ["\r"])
    assert ui.confirm("继续？", default=False) is False


def test_ask_number_tty_parses_value(tty, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("0.02\n"))
    assert ui.ask_number("强度", 0.015) == 0.02


def test_ask_number_tty_rejects_out_of_range(tty, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("99\n"))
    assert ui.ask_number("强度", 0.015, minimum=0.001, maximum=0.1) == 0.015


def test_ask_number_tty_rejects_garbage(tty, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("abc\n"))
    assert ui.ask_number("强度", 0.015) == 0.015


def test_ask_text_tty(tty, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello\n"))
    assert ui.ask_text("名字", "default") == "hello"
