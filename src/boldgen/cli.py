"""命令行入口。

子命令一览::

    boldgen scan          扫描系统字体，列出缺少粗体的家族
    boldgen generate      为指定家族生成粗体 face
    boldgen list          列出已安装的产物
    boldgen check         检测源字体变化导致的产物过期
    boldgen uninstall     移除已安装的产物
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__
from .alias import AliasRule
from .builder import BuildOptions, BuildResult, UnsupportedFontError, build_bold
from .discover import (
    FamilyInfo,
    Face,
    escape_pattern,
    fc_file_families,
    fc_match,
    scan,
)
from .install import (
    INSTALL_DIR,
    ManifestEntry,
    file_sha256,
    install_font,
    load_manifest,
    output_name_for,
    run_fc_cache,
    save_manifest,
    uninstall,
)
from .verify import verify_font

__all__ = ["main", "build_parser"]


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------

def _resolve_family(name: str, families: Sequence[FamilyInfo]) -> Optional[FamilyInfo]:
    """按名字找家族：先精确匹配主名，再匹配任意别名（忽略大小写）。"""
    target = name.strip().lower()
    for info in families:
        if info.key.lower() == target:
            return info
    for info in families:
        for alias in info.names:
            if alias.lower() == target:
                return info
    # 再宽松一点：包含关系
    for info in families:
        for alias in info.names:
            if target and (target in alias.lower() or alias.lower() in target):
                return info
    return None


def _fmt_size(num: int) -> str:
    from .report import format_size

    return format_size(num)


def _default_excludes() -> List[str]:
    """扫描时默认排除的目录：本工具自己的输出目录（否则会自我检测）。"""
    return [INSTALL_DIR]


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> int:
    families = scan(
        cjk_only=not args.all,
        exclude_dirs=list(args.exclude_dir or []) + _default_excludes(),
    )
    if args.missing_bold:
        families = [f for f in families if not f.has_real_bold]

    if args.json:
        payload = [
            {
                "key": info.key,
                "names": info.names,
                "is_cjk": info.is_cjk,
                "has_real_bold": info.has_real_bold,
                "faces": [
                    {
                        "path": face.path,
                        "index": face.index,
                        "style": face.style,
                        "weight": face.weight,
                        "slant": face.slant,
                        "location": face.location,
                    }
                    for face in info.faces
                ],
            }
            for info in families
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not families:
        print("没有找到符合条件的字体家族。")
        return 0

    from .report import render_family_table

    print(f"共 {len(families)} 个字体家族"
          f"{'（仅中文字体）' if not args.all else ''}：")
    print()
    print(render_family_table(families))
    return 0


# --------------------------------------------------------------------------
# generate
# --------------------------------------------------------------------------

def _generate_one(
    info: FamilyInfo,
    face: Face,
    out_path: str,
    options: BuildOptions,
) -> BuildResult:
    return build_bold(face.path, out_path, face_index=face.index, options=options)


def _build_and_install(
    targets: Sequence[FamilyInfo],
    options: BuildOptions,
    install_dir: str,
    dry_run: bool = False,
) -> Tuple[List[BuildResult], List[str]]:
    """生成并（可选）安装一批粗体 face。

    Returns:
        (成功的结果, 失败信息列表)
    """
    os.makedirs(install_dir, exist_ok=True)
    tmp_dir = os.path.join(install_dir, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    entries = load_manifest(install_dir)
    by_output = {entry.output: entry for entry in entries}
    results: List[BuildResult] = []
    failures: List[str] = []

    try:
        for info in targets:
            face = info.source_face
            if face is None:
                failures.append(f"{info.key}：找不到可用的源 face")
                continue
            out_name = output_name_for(info.key, face.postscript_name, options.suffix)
            tmp_path = os.path.join(tmp_dir, out_name)
            try:
                result = _generate_one(info, face, tmp_path, options)
            except UnsupportedFontError as exc:
                failures.append(f"{info.key}：{exc}")
                continue
            except (OSError, ValueError) as exc:
                failures.append(f"{info.key}：生成失败（{exc}）")
                continue

            # 产物是单 face 的 .ttf（face 0），源可能是 .ttc 的第 N 个 face。
            check = verify_font(
                tmp_path, 0, source_path=face.path, source_face_index=face.index
            )
            if not check.ok:
                failures.append(f"{info.key}：自检未通过：" + "；".join(check.errors))
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                continue

            results.append(result)
            if not dry_run:
                install_font(tmp_path, out_name, install_dir)
                # result.output 指向的是临时文件；对外报告最终路径。
                result.output = os.path.join(install_dir, out_name)
                by_output[out_name] = ManifestEntry(
                    output=out_name,
                    source=face.path,
                    source_index=face.index,
                    family=info.key,
                    style=options.suffix,
                    radius=result.radius,
                    strength=options.strength,
                    size=result.size,
                    sha256=file_sha256(os.path.join(install_dir, out_name)),
                    source_sha256=file_sha256(face.path),
                    source_mtime=os.path.getmtime(face.path),
                    generated_at=time.time(),
                )
    finally:
        try:
            for leftover in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, leftover))
            os.rmdir(tmp_dir)
        except OSError:
            pass

    if not dry_run:
        save_manifest(list(by_output.values()), install_dir)
    return results, failures


def cmd_generate(args: argparse.Namespace) -> int:
    families = scan(
        cjk_only=not args.all,
        exclude_dirs=list(args.exclude_dir or []) + _default_excludes(),
    )
    if not args.family:
        print("请用 --family 指定至少一个字体家族（用 `boldgen scan` 查看候选）。")
        return 2

    options = BuildOptions(
        strength=args.strength,
        weight=args.weight,
        suffix=args.suffix,
        materialize=not args.no_materialize,
        miter_limit=args.miter_limit,
    )

    targets: List[FamilyInfo] = []
    for name in args.family:
        info = _resolve_family(name, families)
        if info is None:
            print(f"✗ 找不到字体家族：{name}", file=sys.stderr)
            return 2
        if info in targets:
            continue
        targets.append(info)

    install_dir = args.install_dir or INSTALL_DIR
    results, failures = _build_and_install(targets, options, install_dir, args.dry_run)

    total_size = sum(r.size for r in results)
    if results:
        print(f"✓ 生成 {len(results)} 个粗体 face：")
        for result in results:
            print(
                f"    {result.family:<24} {result.output}  "
                f"字形 {result.num_glyphs}  半径 {result.radius}  "
                f"{_fmt_size(result.size)}"
            )
        print(f"  合计 {_fmt_size(total_size)}")
        if not args.dry_run:
            print(f"  已安装到 {install_dir}")
            if run_fc_cache():
                print("  fontconfig 缓存已刷新")
            else:
                print("  ⚠ fc-cache 执行失败，字体可能需要重启应用后才会生效")
    if failures:
        print()
        print("✗ 部分字体失败：", file=sys.stderr)
        for message in failures:
            print(f"    {message}", file=sys.stderr)
    return 1 if failures else 0


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    install_dir = args.install_dir or INSTALL_DIR
    entries = load_manifest(install_dir)
    if not entries:
        print(f"没有已安装的产物（{install_dir}）。")
        return 0
    if args.json:
        print(json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2))
        return 0
    print(f"已安装 {len(entries)} 个粗体 face（{install_dir}）：")
    print()
    for entry in sorted(entries, key=lambda e: e.family.lower()):
        print(f"  {entry.family:<24} {entry.output:<32} {_fmt_size(entry.size)}")
        print(f"      源: {entry.source}"
              + (f"#{entry.source_index}" if entry.source_index else ""))
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    install_dir = args.install_dir or INSTALL_DIR
    entries = load_manifest(install_dir)
    if not entries:
        print("没有已安装的产物。")
        return 0
    stale: List[str] = []
    missing: List[str] = []
    shadowed: List[str] = []
    aliased: List[str] = []
    for entry in entries:
        target = os.path.join(install_dir, entry.output)
        if not os.path.exists(target):
            missing.append(entry.output)
            continue
        if entry.source_sha256:
            try:
                current = file_sha256(entry.source)
            except OSError:
                missing.append(entry.source)
                continue
            if current != entry.source_sha256:
                stale.append(f"{entry.family}（源文件已变化：{entry.source}）")
        # 加粗请求是否真的落到了产物上？被 fontconfig 别名劫持的话，
        # 产物再完美也不会被用上——这是"装了却没效果"最常见的原因。
        if not args.no_fc_check:
            # 一个家族往往有多个名字（英文名 + 中文名），应用用哪个不确定，
            # 所以每个名字都要查一遍。家族名里的连字符必须转义，否则
            # fontconfig 会把它当成"家族-样式"后缀丢掉，静默匹配失败。
            names = fc_file_families(target) or [entry.family]
            for name in names:
                pattern = escape_pattern(name)
                match = fc_match(f"{pattern}:bold")
                if match is None:
                    continue
                matched = os.path.abspath(str(match["file"]))
                if matched == os.path.abspath(target):
                    continue
                # 加粗被劫持了。看看常规字重是不是也被劫持了：
                # 两者都被劫持说明是 fontconfig 里本来就有的 strong 别名
                # （用户自己配的），跟本工具的产物无关；
                # 只有加粗被劫持才是本工具需要提醒的"装了却没效果"。
                plain = fc_match(pattern)
                plain_file = (
                    os.path.abspath(str(plain["file"])) if plain is not None else ""
                )
                source_file = os.path.abspath(entry.source) if entry.source else ""
                if plain_file and plain_file != source_file:
                    aliased.append(
                        f"{name} → 常规与加粗都指向 {plain['family']}"
                        f"（fontconfig 里本来就有 strong 别名，与产物无关）"
                    )
                else:
                    shadowed.append(
                        f"{name} → 命中 {match['file']}"
                        f"（{match['family']} / {match['style']}），"
                        f"而不是 {entry.output}"
                    )
    if not stale and not missing and not shadowed:
        print(f"✓ {len(entries)} 个产物都是最新的，且加粗请求都能命中。")
        if aliased:
            print()
            print(f"ℹ {len(aliased)} 个家族名被 fontconfig 的 strong 别名整体重定向了")
            print("  （常规字重同样如此，不是本工具造成的）：")
            for item in aliased:
                print(f"    {item}")
            print()
            print("  如果你希望这些英文名也用上本工具的产物，删掉对应的别名规则：")
            print("      grep -rn \"<family>家族名</family>\" ~/.config/fontconfig/ /etc/fonts/conf.d/")
        return 0
    if stale:
        print(f"⚠ {len(stale)} 个产物已过期：")
        for item in stale:
            print(f"    {item}")
    if missing:
        print(f"⚠ {len(missing)} 个文件缺失：")
        for item in missing:
            print(f"    {item}")
    if shadowed:
        print()
        print(f"⚠ {len(shadowed)} 个家族的加粗请求没有命中本工具的产物：")
        for item in shadowed:
            print(f"    {item}")
        print()
        print("  通常是 fontconfig 里有一条 <alias binding=\"strong\"> 规则")
        print("  把这个家族名重定向到了别的字体。检查：")
        print("      grep -rn \"<family>家族名</family>\" ~/.config/fontconfig/ /etc/fonts/conf.d/")
    if aliased:
        print()
        print(f"ℹ {len(aliased)} 个家族名被 fontconfig 的 strong 别名整体重定向了")
        print("  （常规字重同样如此，与产物无关）：")
        for item in aliased:
            print(f"    {item}")
    return 1


# --------------------------------------------------------------------------
# uninstall
# --------------------------------------------------------------------------

def cmd_uninstall(args: argparse.Namespace) -> int:
    install_dir = args.install_dir or INSTALL_DIR
    entries = load_manifest(install_dir)
    if args.all:
        removed = uninstall(entries, install_dir)
    elif args.family:
        wanted = {name.strip().lower() for name in args.family}
        picked = [
            e for e in entries
            if e.family.lower() in wanted or e.output.lower() in wanted
        ]
        removed = uninstall(picked, install_dir, remove_manifest=False)
        save_manifest([e for e in entries if e not in picked], install_dir)
    else:
        print("请指定 --family 名称，或用 --all 移除全部。")
        return 2
    if removed:
        for path in removed:
            print(f"✓ 已删除 {path}")
        if run_fc_cache():
            print("fontconfig 缓存已刷新")
    else:
        print("没有匹配到要删除的产物。")
    return 0


# --------------------------------------------------------------------------
# mktest
# --------------------------------------------------------------------------

#: 没有指定字体时，测试文档里默认用这些家族。
DEFAULT_TEST_FONTS = [
    ("宋体", "SimSun"),
    ("黑体", "SimHei"),
    ("楷体", "KaiTi"),
    ("仿宋", "FangSong"),
]


def cmd_mktest(args: argparse.Namespace) -> int:
    from .mktest import build_test_docx

    families: List[Tuple[str, str]] = []
    if args.font:
        for name in args.font:
            families.append((name, name))
    else:
        # 已安装产物的家族 + 常用中文字体
        seen = set()
        for entry in load_manifest(args.install_dir or INSTALL_DIR):
            if entry.family in seen:
                continue
            seen.add(entry.family)
            families.append((entry.family, entry.family))
        for label, font in DEFAULT_TEST_FONTS:
            if font not in seen:
                seen.add(font)
                families.append((label, font))

    out = args.out or os.path.join(os.getcwd(), "boldgen-test.docx")
    build_test_docx(out, families, sample=args.sample, half_points=args.size)
    print(f"✓ 已生成测试文档：{out}")
    print(f"  包含 {len(families)} 个字体家族，每个两行（加粗 / 常规）。")
    print("  用 WPS / LibreOffice 打开，确认加粗行没有变成黑块。")
    if args.open:
        import shutil
        import subprocess

        launcher = shutil.which("wps") or shutil.which("wpsoffice")
        if launcher is None:
            print("⚠ 找不到 wps 命令，未自动打开。", file=sys.stderr)
            return 1
        subprocess.Popen([launcher, out])
    return 0


# --------------------------------------------------------------------------
# interactive
# --------------------------------------------------------------------------

def cmd_interactive(args: argparse.Namespace) -> int:
    from . import ui
    from .alias import alias_conf_path, load_rules, save_rules
    from .report import format_size

    families = scan(
        cjk_only=not args.all,
        exclude_dirs=list(args.exclude_dir or []) + _default_excludes(),
    )
    candidates = [f for f in families if not f.has_real_bold]
    if args.include_has_bold:
        candidates = families
    if not candidates:
        print("没有找到缺少粗体的字体家族——是不是已经都处理过了？")
        return 0

    print(f"扫描到 {len(candidates)} 个缺少粗体的中文字体家族。")
    try:
        picked = ui.select_families(candidates)
        mode = ui.choose_mode()
    except ui.InteractionCancelled:
        print("已取消。")
        return 0

    if not picked:
        print("没有选中任何家族。")
        return 0

    install_dir = args.install_dir or INSTALL_DIR

    if mode == ui.MODE_GENERATE:
        strength = ui.ask_number("加粗强度（半径 = em × 该系数）", 0.015, 0.001, 0.1)
        weight = int(ui.ask_number("写入的字重值", 700, 100, 900))
        options = BuildOptions(strength=strength, weight=weight)

        print()
        print("── 执行计划 ──")
        for info in picked:
            face = info.source_face
            print(f"  {info.display_name:<34} ← {face.location if face else '-'}")
        print(f"  强度 {strength}   字重 {weight}")
        print(f"  预计产物：{len(picked)} 个 .ttf，装到 {install_dir}")
        if not ui.confirm("开始生成？"):
            print("已取消。")
            return 0

        results, failures = _build_and_install(picked, options, install_dir, args.dry_run)
        print(f"✓ 生成 {len(results)} 个粗体 face，合计 "
              f"{format_size(sum(r.size for r in results))}")
        if not args.dry_run:
            print(f"  已安装到 {install_dir}")
            run_fc_cache()
        for message in failures:
            print(f"✗ {message}", file=sys.stderr)
        return 1 if failures else 0

    # --- 别名模式 ---
    rules = _plan_alias_rules(picked, families, args.target)
    if not rules:
        print("没有可写的别名规则。")
        return 0
    print()
    print("── 执行计划 ──")
    for rule in rules:
        print(f"  {rule.source_family}  →  {rule.target_family}")
    print(f"  写入 {alias_conf_path()}")
    if not ui.confirm("开始写入？"):
        print("已取消。")
        return 0

    existing = load_rules()
    merged = _merge_rules(existing, rules)
    if args.dry_run:
        print("（--dry-run，未写入）")
        return 0
    path = save_rules(merged)
    print(f"✓ 已写入 {path}（共 {len(merged)} 条规则）")
    run_fc_cache()
    print("  fontconfig 缓存已刷新")
    return 0


def _plan_alias_rules(
    picked: Sequence[FamilyInfo],
    all_families: Sequence[FamilyInfo],
    forced_target: Optional[str],
) -> List["AliasRule"]:
    """为选中的家族规划别名规则。"""
    from .alias import AliasRule, recommend_target

    rules: List[AliasRule] = []
    for info in picked:
        if forced_target:
            target = forced_target
        else:
            candidate = recommend_target(info, all_families)
            if candidate is None:
                continue
            target = candidate.key
        for name in [info.key] + [n for n in info.names if n != info.key]:
            rules.append(
                AliasRule(
                    source_family=name,
                    target_family=target,
                    comment=f"{name} → {target}",
                )
            )
    return rules


def _merge_rules(
    existing: Sequence["AliasRule"], new: Sequence["AliasRule"]
) -> List["AliasRule"]:
    """合并规则：同名源家族以新规则覆盖。"""
    merged: Dict[str, "AliasRule"] = {rule.source_family: rule for rule in existing}
    for rule in new:
        merged[rule.source_family] = rule
    return list(merged.values())


# --------------------------------------------------------------------------
# alias
# --------------------------------------------------------------------------

def cmd_alias(args: argparse.Namespace) -> int:
    from .alias import AliasRule, alias_conf_path, load_rules, recommend_target, save_rules

    if args.list:
        rules = load_rules()
        if not rules:
            print(f"没有别名规则（{alias_conf_path()}）。")
            return 0
        print(f"共 {len(rules)} 条规则（{alias_conf_path()}）：")
        for rule in rules:
            print(f"  {rule.source_family}  →  {rule.target_family}")
        return 0

    if args.remove:
        existing = load_rules()
        if args.all:
            removed = existing
            kept: List[AliasRule] = []
        else:
            wanted = {n.strip().lower() for n in (args.family or [])}
            removed = [r for r in existing if r.source_family.lower() in wanted]
            kept = [r for r in existing if r.source_family.lower() not in wanted]
        if args.dry_run:
            print(f"（--dry-run）将删除 {len(removed)} 条规则")
            return 0
        if removed:
            if kept:
                save_rules(kept)
            else:
                path = alias_conf_path()
                if os.path.exists(path):
                    os.remove(path)
            print(f"✓ 已删除 {len(removed)} 条规则")
            run_fc_cache()
        else:
            print("没有匹配的规则。")
        return 0

    families = scan(
        cjk_only=not args.all,
        exclude_dirs=list(args.exclude_dir or []) + _default_excludes(),
    )
    if args.family:
        picked = []
        for name in args.family:
            info = _resolve_family(name, families)
            if info is None:
                print(f"✗ 找不到字体家族：{name}", file=sys.stderr)
                return 2
            picked.append(info)
    else:
        picked = [f for f in families if not f.has_real_bold]

    rules = _plan_alias_rules(picked, families, args.target)
    if not rules:
        print("没有可写的别名规则（找不到合适的粗体目标）。")
        return 0

    print("── 别名规则 ──")
    for rule in rules:
        print(f"  {rule.source_family}  →  {rule.target_family}")
    if args.dry_run:
        print(f"（--dry-run，未写入 {alias_conf_path()}）")
        return 0

    merged = _merge_rules(load_rules(), rules)
    path = save_rules(merged)
    print(f"✓ 已写入 {path}（共 {len(merged)} 条规则）")
    run_fc_cache()
    print("  fontconfig 缓存已刷新")
    return 0


# --------------------------------------------------------------------------
# 参数解析
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boldgen",
        description="为缺少粗体的字体家族烘焙真正的 Bold face。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  boldgen scan                       看看哪些中文字体缺粗体\n"
            "  boldgen generate --family 宋体      给宋体生成粗体\n"
            "  boldgen list                       看已安装了哪些\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"boldgen {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    # --- scan ---
    p_scan = sub.add_parser("scan", help="扫描系统字体，列出缺少粗体的家族")
    p_scan.add_argument("--all", action="store_true", help="不限于中文字体")
    p_scan.add_argument("--missing-bold", action="store_true", help="只显示缺粗体的家族")
    p_scan.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_scan.add_argument("--exclude-dir", action="append", help="扫描时排除的目录（可重复）")
    p_scan.set_defaults(func=cmd_scan)

    # --- generate ---
    p_gen = sub.add_parser("generate", help="为指定家族生成粗体 face")
    p_gen.add_argument("--family", action="append", required=False,
                       help="字体家族名，可重复（中文名/英文名都行）")
    p_gen.add_argument("--strength", type=float, default=0.015,
                       help="加粗系数：半径 = round(unitsPerEm × 系数)，默认 0.015")
    p_gen.add_argument("--weight", type=int, default=700, help="写入的字重值，默认 700")
    p_gen.add_argument("--suffix", default="Bold", help="样式名后缀，默认 Bold")
    p_gen.add_argument("--miter-limit", type=float, default=4.0,
                       help="斜接长度上限倍数，超过退化为斜切，默认 4.0")
    p_gen.add_argument("--no-materialize", action="store_true",
                       help="不把隐含 on-curve 中点物化（文件更小，几何略有偏差）")
    p_gen.add_argument("--all", action="store_true", help="允许处理非中文字体")
    p_gen.add_argument("--dry-run", action="store_true", help="只生成不安装")
    p_gen.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_gen.add_argument("--exclude-dir", action="append", help="扫描时排除的目录（可重复）")
    p_gen.set_defaults(func=cmd_generate)

    # --- list ---
    p_list = sub.add_parser("list", help="列出已安装的产物")
    p_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_list.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_list.set_defaults(func=cmd_list)

    # --- check ---
    p_check = sub.add_parser("check", help="检测产物是否过期")
    p_check.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_check.add_argument("--no-fc-check", action="store_true",
                       help="不检查加粗请求是否真的命中产物（跳过 fc-match）")
    p_check.set_defaults(func=cmd_check)

    # --- uninstall ---
    p_uninstall = sub.add_parser("uninstall", help="移除已安装的产物")
    p_uninstall.add_argument("--family", action="append", help="要移除的家族名，可重复")
    p_uninstall.add_argument("--all", action="store_true", help="移除全部")
    p_uninstall.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # --- mktest ---
    p_mk = sub.add_parser("mktest", help="生成用于人工验证的 docx 测试文档")
    p_mk.add_argument("--out", help="输出路径，默认 ./boldgen-test.docx")
    p_mk.add_argument("--font", action="append", help="要测试的字体名，可重复")
    p_mk.add_argument("--sample", default="中文加粗测试", help="中文样本文字")
    p_mk.add_argument("--size", type=int, default=24, help="字号（半磅），默认 24")
    p_mk.add_argument("--open", action="store_true", help="生成后用 WPS 打开")
    p_mk.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_mk.set_defaults(func=cmd_mktest)

    # --- interactive ---
    p_int = sub.add_parser(
        "interactive", help="交互式：扫描 → 勾选 → 单选处理方式 → 执行"
    )
    p_int.add_argument("--all", action="store_true", help="不限于中文字体")
    p_int.add_argument("--include-has-bold", action="store_true",
                       help="把已有粗体的家族也列进候选")
    p_int.add_argument("--dry-run", action="store_true", help="只生成不安装")
    p_int.add_argument("--target", help="别名模式下统一指定目标粗体家族")
    p_int.add_argument("--install-dir", help=f"安装目录，默认 {INSTALL_DIR}")
    p_int.add_argument("--exclude-dir", action="append", help="扫描时排除的目录（可重复）")
    p_int.set_defaults(func=cmd_interactive)

    # --- alias ---
    p_alias = sub.add_parser(
        "alias", help="fontconfig 别名模式：把加粗请求映射到已有的粗体"
    )
    p_alias.add_argument("--family", action="append", help="源字体家族，可重复")
    p_alias.add_argument("--target", help="目标粗体家族（不给则按类别自动推荐）")
    p_alias.add_argument("--list", action="store_true", help="列出已有规则")
    p_alias.add_argument("--remove", action="store_true", help="删除规则")
    p_alias.add_argument("--all", action="store_true", help="对全部缺粗体的家族生效 / 删除全部")
    p_alias.add_argument("--dry-run", action="store_true", help="只预览不写入")
    p_alias.add_argument("--exclude-dir", action="append", help="扫描时排除的目录（可重复）")
    p_alias.set_defaults(func=cmd_alias)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print()
        return 130
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
