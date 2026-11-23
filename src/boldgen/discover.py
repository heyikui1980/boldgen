"""扫描系统字体，找出**缺少粗体**的家族。

数据来源是 fontconfig 的 ``fc-list``——它是 Linux 上字体事实上的标准查询
接口，能一次性给出家族名、样式名、字重、slant、以及文件路径与 face 序号。

两个关键细节：

* ``fc-list`` 的 ``%{weight}`` 是**缩放刻度**（Regular=80、SemiBold=180、
  Bold=200、ExtraBold=205、Black=210），不是 CSS 的 100–900。
  用 ``>= 600`` 判断粗体会全部漏判。
* ``%{family}`` 与 ``%{style}`` 都是逗号分隔的多值列表，第一个是主名。
"""

from __future__ import annotations

import os
import struct
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .cjk import CJK_SAMPLE_CODEPOINTS, is_cjk_name
from .sfnt import Font

__all__ = [
    "Face",
    "FamilyInfo",
    "scan",
    "probe_font",
    "fc_match",
    "escape_pattern",
    "fc_file_families",
    "BOLD_WEIGHT_THRESHOLD",
    "REGULAR_WEIGHT",
]

#: fontconfig 缩放刻度上的"粗体"门槛（Bold=200，ExtraBold=205，Black=210）。
BOLD_WEIGHT_THRESHOLD = 200

#: fontconfig 缩放刻度上的 Regular。
REGULAR_WEIGHT = 80

#: fc-list 输出格式：文件、face 序号、家族、样式、字重、slant、全名、PostScript 名。
#: 注意 fc-list 的 ``--format`` 不会自动补换行，必须自己带上。
_FC_FORMAT = (
    "%{file}\t%{index}\t%{family}\t%{style}\t%{weight}\t%{slant}"
    "\t%{fullname}\t%{postscriptname}\n"
)

#: 变量字体的命名实例在 ``%{index}`` 里是 0x10000 起步的。
_VARIABLE_INSTANCE_BASE = 0x10000


@dataclass
class Face:
    """一个字体 face。"""

    path: str
    index: int
    family: str
    families: List[str]
    style: str
    styles: List[str]
    weight: int
    slant: int
    fullname: str = ""
    postscript_name: str = ""
    covers_han: bool = False
    is_collection: bool = False
    has_fvar: bool = False

    @property
    def is_bold(self) -> bool:
        return self.weight >= BOLD_WEIGHT_THRESHOLD

    @property
    def is_italic(self) -> bool:
        return self.slant != 0

    @property
    def location(self) -> str:
        """人类可读的定位串。"""
        if self.is_collection:
            return f"{self.path}#{self.index}"
        return self.path


@dataclass
class FamilyInfo:
    """一个字体家族及其所有 face。"""

    key: str
    names: List[str]
    faces: List[Face] = field(default_factory=list)
    is_cjk: bool = False

    @property
    def has_real_bold(self) -> bool:
        """家族里是否已有真正的粗体 face。"""
        return any(face.is_bold and not face.is_italic for face in self.faces)

    @property
    def has_bold_any_slant(self) -> bool:
        return any(face.is_bold for face in self.faces)

    @property
    def source_face(self) -> Optional[Face]:
        """建议用来合成粗体的源 face。

        规则：先只要正体（slant == 0），再优先 Regular 字重；
        同等条件下取 face 序号最小的那个（同一 TTC 里通常是主 face）。
        """
        upright = [f for f in self.faces if not f.is_italic]
        pool = upright or list(self.faces)
        regular = [f for f in pool if f.weight == REGULAR_WEIGHT]
        if regular:
            pool = regular
        else:
            lightest = min(f.weight for f in pool)
            pool = [f for f in pool if f.weight == lightest]
        return sorted(pool, key=lambda f: (f.index, f.path))[0]

    @property
    def display_name(self) -> str:
        """显示用名称：主名 + （中文别名）。"""
        primary = self.names[0] if self.names else self.key
        others = [n for n in self.names[1:] if n != primary]
        cjk_names = [n for n in others if is_cjk_name(n)]
        if cjk_names:
            return f"{primary} ({'/'.join(cjk_names)})"
        return primary


def probe_font(path: str) -> Dict[str, object]:
    """快速探测字体文件结构（只读文件头部）。"""
    info: Dict[str, object] = {
        "is_collection": False,
        "num_faces": 1,
        "has_fvar": False,
        "has_glyf": False,
    }
    try:
        with open(path, "rb") as handle:
            head = handle.read(12)
            if head[:4] == b"ttcf":
                info["is_collection"] = True
                info["num_faces"] = struct.unpack_from(">I", head, 8)[0]
                handle.seek(0)
                blob = handle.read()
            else:
                handle.seek(0)
                blob = head + handle.read(8192)
        font = Font(blob, 0)
        info["has_fvar"] = font.has_table("fvar")
        info["has_glyf"] = font.has_table("glyf")
    except (OSError, ValueError, struct.error):
        pass
    return info


def _run_fc_list(charset: Optional[str] = None) -> List[str]:
    """调用 fc-list，返回原始行。"""
    cmd = ["fc-list"]
    if charset:
        cmd.append(f":charset={charset}")
    cmd.append(f"--format={_FC_FORMAT}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "找不到 fc-list 命令。请安装 fontconfig（Debian/Ubuntu: apt install fontconfig）。"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(f"fc-list 执行失败：{proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _parse_line(line: str) -> Optional[Face]:
    parts = line.split("\t")
    if len(parts) < 6:
        return None
    path, index_s, families_s, styles_s, weight_s, slant_s = parts[:6]
    fullname = parts[6] if len(parts) > 6 else ""
    postscript = parts[7] if len(parts) > 7 else ""
    try:
        index = int(index_s)
        weight = int(weight_s)
        slant = int(slant_s)
    except ValueError:
        return None
    families = [f.strip() for f in families_s.split(",") if f.strip()]
    styles = [s.strip() for s in styles_s.split(",") if s.strip()]
    if not families:
        return None
    return Face(
        path=path,
        index=index,
        family=families[0],
        families=families,
        style=styles[0] if styles else "Regular",
        styles=styles,
        weight=weight,
        slant=slant,
        fullname=fullname,
        postscript_name=postscript,
    )


def scan(
    cjk_only: bool = True,
    exclude_dirs: Sequence[str] = (),
    exclude_paths: Sequence[str] = (),
) -> List[FamilyInfo]:
    """扫描系统字体，返回按家族分组的列表。

    Args:
        cjk_only: 只保留中文字体。
        exclude_dirs: 排除这些目录下的字体（例如本工具自己的输出目录，
            否则刚生成的粗体会让源家族看起来"已经有粗体"）。
        exclude_paths: 排除这些具体文件。

    Returns:
        按主家族名排序的 :class:`FamilyInfo` 列表。
    """
    exclude_dirs = [
        os.path.abspath(os.path.expanduser(d)) for d in exclude_dirs if d
    ]
    exclude_paths = {os.path.abspath(os.path.expanduser(p)) for p in exclude_paths}

    def excluded(path: str) -> bool:
        ap = os.path.abspath(path)
        if ap in exclude_paths:
            return True
        return any(ap.startswith(d + os.sep) or ap == d for d in exclude_dirs)

    # 先查覆盖汉字的字体
    han_paths: set = set()
    if cjk_only:
        for line in _run_fc_list(charset=f"{CJK_SAMPLE_CODEPOINTS[0]:x}"):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            han_paths.add((parts[0], parts[1]))

    faces: List[Face] = []
    probe_cache: Dict[str, Dict[str, object]] = {}

    def probe(path: str) -> Dict[str, object]:
        if path not in probe_cache:
            probe_cache[path] = probe_font(path)
        return probe_cache[path]

    for line in _run_fc_list():
        face = _parse_line(line)
        if face is None:
            continue
        if excluded(face.path):
            continue
        # 变量字体的命名实例：跳过，只用默认实例
        if face.index >= _VARIABLE_INSTANCE_BASE:
            continue
        face.covers_han = (face.path, str(face.index)) in han_paths
        info = probe(face.path)
        face.is_collection = bool(info["is_collection"])
        face.has_fvar = bool(info["has_fvar"])
        faces.append(face)

    # 分组
    groups: Dict[str, FamilyInfo] = {}
    for face in faces:
        info = groups.get(face.family)
        if info is None:
            info = FamilyInfo(key=face.family, names=[], faces=[])
            groups[face.family] = info
        info.faces.append(face)
        for name in face.families:
            if name not in info.names:
                info.names.append(name)

    result: List[FamilyInfo] = []
    for info in groups.values():
        info.is_cjk = any(f.covers_han for f in info.faces) or is_cjk_name(*info.names)
        if cjk_only and not info.is_cjk:
            continue
        result.append(info)

    result.sort(key=lambda i: (not i.is_cjk, i.key.lower()))
    return result


def missing_bold(
    cjk_only: bool = True,
    exclude_dirs: Sequence[str] = (),
) -> List[FamilyInfo]:
    """只返回**缺少真粗体**的家族。"""
    return [
        info
        for info in scan(cjk_only=cjk_only, exclude_dirs=exclude_dirs)
        if not info.has_real_bold
    ]


#: fontconfig 模式字符串里需要转义的字符。
#:
#: ``FcNameParse`` 用 ``:`` 分属性、``,`` 分值、``=`` 赋值，反斜杠转义。
#: 空格是安全的（``"Noto Sans CJK SC"`` 本来就能解析）。
_PATTERN_SPECIALS = "\\:,="


def escape_pattern(value: str) -> str:
    """把家族名转义成 fontconfig 模式里安全的字面量。

    **连字符必须转义**：``FcNameParse`` 会把家族名里**第一个连字符之后的
    整段**当成"样式后缀"丢掉——``fc-pattern "SimSun-Bold"`` 解析出来是
    ``family="SimSun"``，``fc-pattern "FZFangSong-Z02"`` 解析出来是
    ``family="FZFangSong"``。不转义的话，这类家族名永远匹配不上任何字体，
    ``fc-match`` 会静默回落到 sans-serif。

    转义写法是 ``"FZFangSong\\-Z02"``（反斜杠 + 原字符）。
    """
    out: List[str] = []
    for ch in value:
        if ch in _PATTERN_SPECIALS or ch == "-":
            out.append("\\")
        out.append(ch)
    return "".join(out)


def fc_file_families(path: str) -> List[str]:
    """某个字体文件在 fontconfig 看来属于哪些家族名。

    一个中文字体通常同时有英文名和中文名（``"FZFangSong-Z02,方正仿宋_GBK"``），
    应用用哪个名字请求加粗是不确定的，所以自检要把所有名字都查一遍。
    """
    fmt = "%{family}\n"
    try:
        proc = subprocess.run(
            ["fc-list", f"--format={fmt}", os.path.abspath(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    names: List[str] = []
    for line in proc.stdout.splitlines():
        for item in line.split(","):
            item = item.strip()
            if item and item not in names:
                names.append(item)
    return names


def fc_match(pattern: str) -> Optional[Dict[str, object]]:
    """查询 fontconfig 对某个模式的最优匹配。

    用途：确认"某家族 + 加粗"的请求**确实**落到了本工具生成的产物上。
    如果中间有 fontconfig 别名规则（``<alias binding="strong">``）把家族名
    重定向到别的字体，加粗请求就会被劫持——生成得再好也没用。

    传入的应该是**模式字符串**（如 ``"SimSun:bold"``），不是裸家族名；
    裸家族名请先过 :func:`escape_pattern`。

    Returns:
        含 ``file`` / ``family`` / ``style`` / ``weight`` 的字典；
        查询失败时返回 None。
    """
    fmt = "%{file}\t%{family}\t%{style}\t%{weight}\n"
    try:
        proc = subprocess.run(
            ["fc-match", f"--format={fmt}", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    line = proc.stdout.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 4:
        return None
    try:
        weight = int(parts[3])
    except ValueError:
        weight = 0
    return {
        "pattern": pattern,
        "file": parts[0],
        "family": parts[1],
        "style": parts[2],
        "weight": weight,
    }
