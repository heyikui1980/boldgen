"""fontconfig 别名模式。

**别名模式**与**生成器模式**是两种互补的思路：

* 生成器模式：离线烘焙出真正的 Bold 字体文件。字形不变，只是变粗。
  效果最好，但每个家族都要多占一份磁盘（中文大字体动辄几十 MB）。
* 别名模式：写一条 fontconfig 规则，把"该家族 + 加粗"的请求重定向到
  另一个**已经**有粗体的家族。零额外磁盘占用，但字形会变成目标字体的。

别名规则只影响**加粗请求**，常规字重完全不受影响::

    <match target="pattern">
      <test name="family" compare="eq"><string>SimSun</string></test>
      <test name="weight" compare="more_eq"><const>bold</const></test>
      <edit name="family" mode="assign"><string>Noto Serif CJK SC</string></edit>
    </match>

注意 fontconfig 的 ``%{weight}`` 是**缩放刻度**（Regular=80、SemiBold=180、
Bold=200、ExtraBold=205、Black=210），``<const>bold</const>`` 会被解析成 200，
因此 ``more_eq`` 能正确命中"粗体及以上"。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .discover import FamilyInfo

__all__ = [
    "AliasRule",
    "ALIAS_CONF_NAME",
    "alias_conf_path",
    "build_alias_xml",
    "load_rules",
    "save_rules",
    "classify_family",
    "recommend_target",
    "CATEGORY_KEYWORDS",
]

#: 生成的别名配置文件名（放在用户级 ``conf.d`` 里，编号 99 保证最后生效）。
ALIAS_CONF_NAME = "99-boldgen-aliases.conf"

#: 字体类别关键词 → 类别名。按顺序匹配，先匹配到的优先。
CATEGORY_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("kai", ("楷", "Kai", "楷体")),
    ("fangsong", ("仿宋", "FangSong", "Fang")),
    ("xiaobiaosong", ("小标宋", "XiaoBiaoSong")),
    ("lishu", ("隶书", "LiSu", "Lishu")),
    ("xingshu", ("行楷", "行书", "Xingkai", "XingKai")),
    ("weibei", ("魏碑", "XinWei")),
    ("hupo", ("琥珀", "Hupo")),
    ("caiyun", ("彩云", "Caiyun", "CaiYun")),
    ("yuan", ("圆", "Yuan")),
    ("hei", ("黑体", "Hei", "Sans", "Gothic", "雅黑", "YaHei", "Sans CJK", "HeiTi")),
    ("song", ("宋", "Song", "Ming", "明朝", "Sun", "Sung", "MingLiU", "Serif")),
)

#: 各类别对应的推荐目标（家族名关键字）。第一个能被匹配上的就用。
_CATEGORY_TARGETS: Dict[str, Tuple[str, ...]] = {
    "song": ("Noto Serif CJK SC", "AR PL UMing CN", "Source Han Serif"),
    "hei": ("Noto Sans CJK SC", "WenQuanYi Zen Hei", "Source Han Sans"),
    "kai": ("Noto Serif CJK SC", "AR PL UKai CN"),
    "fangsong": ("Noto Serif CJK SC",),
    "xiaobiaosong": ("Noto Serif CJK SC",),
    "lishu": ("Noto Serif CJK SC",),
    "xingshu": ("Noto Serif CJK SC",),
    "weibei": ("Noto Serif CJK SC",),
    "hupo": ("Noto Serif CJK SC",),
    "caiyun": ("Noto Serif CJK SC",),
    "yuan": ("Noto Sans CJK SC",),
}

#: 兜底目标。
_FALLBACK_TARGETS = ("Noto Serif CJK SC", "Noto Sans CJK SC")


@dataclass
class AliasRule:
    """一条别名规则。"""

    source_family: str
    target_family: str
    comment: str = ""


def alias_conf_path() -> str:
    """用户级 fontconfig 别名配置文件的路径。"""
    return os.path.join(
        os.path.expanduser("~"), ".config", "fontconfig", "conf.d", ALIAS_CONF_NAME
    )


def build_alias_xml(rules: Sequence[AliasRule]) -> str:
    """把规则渲染成 fontconfig 配置。"""
    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">',
        "<!-- 由 boldgen 生成；删除本文件即可全部撤销。 -->",
        "<fontconfig>",
    ]
    for rule in rules:
        if rule.comment:
            lines.append(f"  <!-- {rule.comment} -->")
        lines.append('  <match target="pattern">')
        lines.append('    <test name="family" compare="eq">')
        lines.append(f"      <string>{_xml_escape(rule.source_family)}</string>")
        lines.append("    </test>")
        lines.append('    <test name="weight" compare="more_eq">')
        lines.append("      <const>bold</const>")
        lines.append("    </test>")
        lines.append('    <edit name="family" mode="assign">')
        lines.append(f"      <string>{_xml_escape(rule.target_family)}</string>")
        lines.append("    </edit>")
        lines.append("  </match>")
    lines.append("</fontconfig>")
    return "\n".join(lines) + "\n"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_RULE_RE = re.compile(
    r'<test name="family" compare="eq">\s*<string>([^<]*)</string>\s*</test>.*?'
    r'<edit name="family" mode="assign">\s*<string>([^<]*)</string>\s*</edit>',
    re.DOTALL,
)


def load_rules(path: Optional[str] = None) -> List[AliasRule]:
    """读回已生成的别名规则。"""
    target = path or alias_conf_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return []
    rules: List[AliasRule] = []
    for match in _RULE_RE.finditer(content):
        rules.append(AliasRule(source_family=match.group(1), target_family=match.group(2)))
    return rules


def save_rules(rules: Sequence[AliasRule], path: Optional[str] = None) -> str:
    """写入别名规则。"""
    target = path or alias_conf_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(build_alias_xml(rules))
    return target


def classify_family(name: str) -> str:
    """判断字体类别（song/hei/kai/fangsong/…）。"""
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in name:
                return category
    return "other"


def recommend_target(
    source: FamilyInfo,
    families: Sequence[FamilyInfo],
) -> Optional[FamilyInfo]:
    """给一个家族推荐目标粗体家族。

    评分规则：

    1. 目标必须有真粗体；
    2. 类别相同优先（宋体 → 宋体类粗体，楷体 → 楷体类粗体）；
    3. 同类别没有合适的，退到该类别的默认目标（Noto Serif/Sans CJK SC）；
    4. 目标也必须是中文字体。
    """
    category = classify_family(source.key)
    for name in source.names:
        other = classify_family(name)
        if other != "other":
            category = other
            break

    candidates = [
        info
        for info in families
        if info.has_real_bold and info.is_cjk and info.key != source.key
    ]
    if not candidates:
        return None

    def score(info: FamilyInfo) -> tuple:
        same_category = 0 if classify_family(info.key) == category else 1
        preferred = _CATEGORY_TARGETS.get(category, ())
        preferred_rank = len(preferred)
        for index, name in enumerate(preferred):
            if name.lower() in info.key.lower() or info.key.lower() in name.lower():
                preferred_rank = index
                break
        return (same_category, preferred_rank, info.key.lower())

    candidates.sort(key=score)
    best = candidates[0]
    # 同类别完全没有候选时，退到类别默认目标
    if classify_family(best.key) != category:
        for name in _CATEGORY_TARGETS.get(category, ()) + _FALLBACK_TARGETS:
            for info in candidates:
                if info.key.lower() == name.lower():
                    return info
    return best
