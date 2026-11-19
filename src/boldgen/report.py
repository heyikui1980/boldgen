"""输出格式化：把扫描结果与生成结果渲染成对齐的表格。

纯文本表格不依赖终端宽度（按内容计算列宽），既能给人看，也能塞进日志。
"""

from __future__ import annotations

import os
from typing import Dict, List, Sequence

from .builder import BuildResult
from .discover import FamilyInfo

__all__ = [
    "format_size",
    "render_family_table",
    "render_build_table",
    "family_to_dict",
    "build_result_to_dict",
]


def format_size(num: float) -> str:
    """把字节数格式化成人类可读的大小。"""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _pad(text: str, width: int) -> str:
    """按**显示宽度**补空格（CJK 字符占两列）。"""
    import unicodedata

    display = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - display)


def render_family_table(families: Sequence[FamilyInfo]) -> str:
    """渲染字体家族表。"""
    if not families:
        return "（没有符合条件的字体家族）"
    rows: List[List[str]] = []
    for info in families:
        source = info.source_face
        rows.append(
            [
                info.display_name,
                "有粗体" if info.has_real_bold else "缺粗体",
                "是" if info.is_cjk else "",
                source.location if source else "-",
            ]
        )
    headers = ["家族", "状态", "中文", "源文件"]
    widths = [
        max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(len(headers))
    ]
    lines = [
        "  ".join(_pad(headers[i], widths[i]) for i in range(len(headers))).rstrip(),
        "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    for row in rows:
        lines.append(
            "  ".join(_pad(row[i], widths[i]) for i in range(len(headers))).rstrip()
        )
    return "\n".join(lines)


def render_build_table(results: Sequence[BuildResult]) -> str:
    """渲染生成结果表。"""
    if not results:
        return "（没有产物）"
    rows: List[List[str]] = []
    for result in results:
        rows.append(
            [
                result.family,
                str(result.num_glyphs),
                str(result.radius),
                format_size(result.size),
                os.path.basename(result.output),
            ]
        )
    headers = ["家族", "字形数", "半径", "大小", "文件"]
    widths = [
        max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(len(headers))
    ]
    lines = [
        "  ".join(_pad(headers[i], widths[i]) for i in range(len(headers))).rstrip(),
        "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    for row in rows:
        lines.append(
            "  ".join(_pad(row[i], widths[i]) for i in range(len(headers))).rstrip()
        )
    return "\n".join(lines)


def family_to_dict(info: FamilyInfo) -> Dict:
    """家族 → JSON 友好的字典。"""
    source = info.source_face
    return {
        "key": info.key,
        "names": info.names,
        "is_cjk": info.is_cjk,
        "has_real_bold": info.has_real_bold,
        "source": source.location if source else None,
        "faces": [
            {
                "path": face.path,
                "index": face.index,
                "style": face.style,
                "weight": face.weight,
                "slant": face.slant,
            }
            for face in info.faces
        ],
    }


def build_result_to_dict(result: BuildResult) -> Dict:
    """生成结果 → JSON 友好的字典。"""
    return {
        "output": result.output,
        "source": result.source,
        "face_index": result.face_index,
        "family": result.family,
        "style": result.style,
        "postscript_name": result.postscript_name,
        "num_glyphs": result.num_glyphs,
        "changed": result.changed,
        "radius": result.radius,
        "size": result.size,
    }
