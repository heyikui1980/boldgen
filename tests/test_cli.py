"""命令行接口的测试。

这些测试不碰系统字体目录：用 monkeypatch 把 ``scan`` 换成一个假的家族列表，
所有产物都写进 pytest 的临时目录。
"""

from __future__ import annotations

import json
import os

import pytest

from boldgen import cli
from boldgen.discover import Face, FamilyInfo


def _face(family, style="Regular", weight=80, slant=0, path="/tmp/fake.ttf", index=0):
    return Face(
        path=path,
        index=index,
        family=family,
        families=[family],
        style=style,
        styles=[style],
        weight=weight,
        slant=slant,
        fullname=f"{family} {style}",
        postscript_name=f"{family}-{style}",
    )


@pytest.fixture
def fake_font(tmp_path):
    """造一个真的字体文件，供 generate 用。"""
    from conftest import SQUARE, make_font_bytes

    path = tmp_path / "Fake.ttf"
    path.write_bytes(make_font_bytes([SQUARE], family="FakeFamily"))
    return str(path)


@pytest.fixture
def patched_scan(monkeypatch, fake_font):
    family = FamilyInfo(
        key="FakeFamily",
        names=["FakeFamily", "假字体"],
        faces=[_face("FakeFamily", path=fake_font)],
        is_cjk=True,
    )
    monkeypatch.setattr(cli, "scan", lambda **kwargs: [family])
    # 不真的跑 fc-cache（会扫全系统字体目录，又慢又脏）
    monkeypatch.setattr(cli, "run_fc_cache", lambda verbose=False: True)
    return family


def test_scan_prints_table(capsys, patched_scan):
    assert cli.main(["scan"]) == 0
    out = capsys.readouterr().out
    assert "FakeFamily" in out
    assert "缺粗体" in out


def test_scan_json(capsys, patched_scan):
    assert cli.main(["scan", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["key"] == "FakeFamily"
    assert payload[0]["has_real_bold"] is False


def test_generate_installs_and_writes_manifest(tmp_path, capsys, patched_scan):
    install_dir = str(tmp_path / "installed")
    code = cli.main(
        ["generate", "--family", "FakeFamily", "--install-dir", install_dir]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "生成 1 个粗体 face" in out

    files = [n for n in os.listdir(install_dir) if n.endswith(".ttf")]
    assert len(files) == 1
    assert os.path.exists(os.path.join(install_dir, "manifest.json"))


def test_generate_dry_run_installs_nothing(tmp_path, patched_scan):
    install_dir = str(tmp_path / "installed")
    code = cli.main(
        ["generate", "--family", "FakeFamily", "--install-dir", install_dir, "--dry-run"]
    )
    assert code == 0
    files = os.listdir(install_dir) if os.path.isdir(install_dir) else []
    assert not [n for n in files if n.endswith(".ttf")]


def test_generate_unknown_family(tmp_path, capsys, patched_scan):
    code = cli.main(
        ["generate", "--family", "不存在", "--install-dir", str(tmp_path / "x")]
    )
    assert code == 2
    assert "找不到字体家族" in capsys.readouterr().err


def test_generate_accepts_chinese_alias(tmp_path, patched_scan):
    install_dir = str(tmp_path / "installed")
    assert cli.main(["generate", "--family", "假字体", "--install-dir", install_dir]) == 0
    assert [n for n in os.listdir(install_dir) if n.endswith(".ttf")]


def test_list_and_check(tmp_path, capsys, patched_scan):
    install_dir = str(tmp_path / "installed")
    cli.main(["generate", "--family", "FakeFamily", "--install-dir", install_dir])
    capsys.readouterr()

    assert cli.main(["list", "--install-dir", install_dir]) == 0
    assert "FakeFamily" in capsys.readouterr().out

    assert cli.main(["check", "--install-dir", install_dir]) == 0
    assert "都是最新的" in capsys.readouterr().out


def test_check_detects_stale_source(tmp_path, capsys, patched_scan, fake_font):
    install_dir = str(tmp_path / "installed")
    cli.main(["generate", "--family", "FakeFamily", "--install-dir", install_dir])
    capsys.readouterr()

    # 改动源文件 → sha256 变化 → 产物过期
    with open(fake_font, "ab") as handle:
        handle.write(b"\x00" * 8)

    assert cli.main(["check", "--install-dir", install_dir]) == 1
    assert "已过期" in capsys.readouterr().out


def test_uninstall_removes_files(tmp_path, capsys, patched_scan):
    install_dir = str(tmp_path / "installed")
    cli.main(["generate", "--family", "FakeFamily", "--install-dir", install_dir])
    capsys.readouterr()

    assert cli.main(["uninstall", "--all", "--install-dir", install_dir]) == 0
    # 目录被清空后会自动移除
    remaining = os.listdir(install_dir) if os.path.isdir(install_dir) else []
    assert not [n for n in remaining if n.endswith(".ttf")]
    assert cli.main(["list", "--install-dir", install_dir]) == 0
    assert "没有已安装的产物" in capsys.readouterr().out


def test_mktest_creates_docx(tmp_path, patched_scan):
    out = tmp_path / "test.docx"
    assert cli.main(["mktest", "--out", str(out)]) == 0
    assert out.exists()


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "boldgen" in capsys.readouterr().out


def test_alias_dry_run(tmp_path, capsys, monkeypatch, patched_scan):
    """别名模式的 dry-run 不应写任何文件。"""
    from boldgen.alias import AliasRule

    monkeypatch.setattr(
        cli,
        "_plan_alias_rules",
        lambda picked, all_families, forced: [AliasRule("FakeFamily", "Noto Sans CJK SC")],
    )
    conf = tmp_path / "99-boldgen-aliases.conf"
    monkeypatch.setattr("boldgen.alias.alias_conf_path", lambda: str(conf))
    monkeypatch.setattr("boldgen.alias.load_rules", lambda path=None: [])
    monkeypatch.setattr("boldgen.alias.save_rules", lambda rules, path=None: str(conf))

    assert cli.main(["alias", "--family", "FakeFamily", "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert not conf.exists()


def test_alias_writes_rules(tmp_path, capsys, monkeypatch, patched_scan):
    from boldgen.alias import AliasRule

    written = {}

    def fake_save(rules, path=None):
        written["rules"] = list(rules)
        written["path"] = path
        return path or str(tmp_path / "aliases.conf")

    monkeypatch.setattr(
        cli,
        "_plan_alias_rules",
        lambda picked, all_families, forced: [AliasRule("FakeFamily", "Noto Sans CJK SC")],
    )
    monkeypatch.setattr("boldgen.alias.alias_conf_path", lambda: str(tmp_path / "aliases.conf"))
    monkeypatch.setattr("boldgen.alias.load_rules", lambda path=None: [])
    monkeypatch.setattr("boldgen.alias.save_rules", fake_save)
    monkeypatch.setattr(cli, "run_fc_cache", lambda: True)

    assert cli.main(["alias", "--family", "FakeFamily"]) == 0
    assert written["rules"][0].source_family == "FakeFamily"
    assert written["rules"][0].target_family == "Noto Sans CJK SC"


def test_plan_alias_rules_comment_names_the_aliased_family(patched_scan):
    """每条规则的注释要写**被重定向的那个名字**，不是家族的主名。

    一个家族往往有多个名字（SimSun / 宋体），规则注释要能对上号。
    """
    rules = cli._plan_alias_rules(
        [patched_scan], [patched_scan], forced_target="Noto Serif CJK SC"
    )
    assert [r.source_family for r in rules] == ["FakeFamily", "假字体"]
    assert [r.comment for r in rules] == [
        "FakeFamily → Noto Serif CJK SC",
        "假字体 → Noto Serif CJK SC",
    ]
