"""安装 / 卸载 / 清单管理。

产物默认落在 ``~/.local/share/fonts/boldgen/``——这是唯一**不需要 sudo**
就能让 fontconfig 看到新字体的目录（``~/.fonts`` 在现代发行版上已不再
被默认扫描）。

同目录下的 ``manifest.json`` 记录每个产物的来源、参数与校验和，用于：

* ``boldgen list`` 列出已安装的产物；
* ``boldgen check`` 检测源字体是否已变化（产物是否过期）；
* ``boldgen uninstall`` 精确移除本工具生成的文件。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

__all__ = [
    "INSTALL_DIR",
    "MANIFEST_PATH",
    "ManifestEntry",
    "manifest_path",
    "load_manifest",
    "save_manifest",
    "file_sha256",
    "install_font",
    "uninstall",
    "run_fc_cache",
    "output_name_for",
]

#: 默认安装目录。
INSTALL_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "share", "fonts", "boldgen"
)

#: 清单文件名。
MANIFEST_NAME = "manifest.json"


def manifest_path(install_dir: Optional[str] = None) -> str:
    return os.path.join(install_dir or INSTALL_DIR, MANIFEST_NAME)


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    """计算文件的 sha256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@dataclass
class ManifestEntry:
    """清单里的一条记录。"""

    output: str
    source: str
    source_index: int = 0
    family: str = ""
    style: str = "Bold"
    radius: int = 0
    strength: float = 0.0
    size: int = 0
    sha256: str = ""
    source_sha256: str = ""
    source_mtime: float = 0.0
    generated_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestEntry":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def load_manifest(install_dir: Optional[str] = None) -> List[ManifestEntry]:
    """读取清单；不存在返回空列表。"""
    path = manifest_path(install_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    return [ManifestEntry.from_dict(item) for item in entries if isinstance(item, dict)]


def save_manifest(entries: Sequence[ManifestEntry], install_dir: Optional[str] = None) -> str:
    """写入清单。"""
    path = manifest_path(install_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": time.time(),
        "entries": [entry.to_dict() for entry in entries],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def _slug(text: str) -> str:
    """把名字变成安全的文件名词干。"""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", text).strip("-.")
    return cleaned or "font"


def output_name_for(family: str, postscript_name: str = "", suffix: str = "Bold") -> str:
    """生成产物的文件名。"""
    base = _slug(postscript_name) if postscript_name else ""
    if not base or len(base) < 2:
        base = _slug(family)
    if base.lower().endswith(f"-{suffix.lower()}"):
        return f"{base}.ttf"
    return f"{base}-{suffix}.ttf"


def install_font(
    built_path: str,
    out_name: str,
    install_dir: Optional[str] = None,
) -> str:
    """把生成好的字体复制到安装目录。"""
    target_dir = install_dir or INSTALL_DIR
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, out_name)
    shutil.copyfile(built_path, target)
    return target


def uninstall(
    entries: Optional[Sequence[ManifestEntry]] = None,
    install_dir: Optional[str] = None,
    remove_manifest: bool = True,
) -> List[str]:
    """移除产物文件，返回被删除的路径列表。"""
    target_dir = install_dir or INSTALL_DIR
    if entries is None:
        entries = load_manifest(target_dir)
    removed: List[str] = []
    for entry in entries:
        path = os.path.join(target_dir, entry.output)
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)
    if remove_manifest:
        path = manifest_path(target_dir)
        if os.path.exists(path):
            os.remove(path)
    # 清掉空目录
    try:
        if os.path.isdir(target_dir) and not os.listdir(target_dir):
            os.rmdir(target_dir)
    except OSError:
        pass
    return removed


def run_fc_cache(verbose: bool = False) -> bool:
    """刷新 fontconfig 缓存。返回是否成功。"""
    if shutil.which("fc-cache") is None:
        return False
    try:
        proc = subprocess.run(
            ["fc-cache", "-f"], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    if verbose and proc.stderr.strip():
        print(proc.stderr.strip())
    return proc.returncode == 0
