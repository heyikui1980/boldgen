"""boldgen —— 为缺少粗体的字体家族烘焙真正的 Bold face。

背景
----
很多中文字体（宋体、黑体、楷体、仿宋、方正系列、华文系列……）只提供
Regular 一个字重。当文档要求加粗时，应用必须自己做"合成粗体"
（synthetic bold）——即把字形轮廓向外扩张。

各家应用的合成粗体实现质量参差不齐。WPS Office for Linux 的 Writer
渲染器（``libkso.so``）自己实现了一套轮廓扩张，半径被放大了数倍，
中文加粗会渲染成一团涂抹状的黑块。

本工具的做法很直接：**离线把粗体烘焙进字体文件**。生成出来的 Bold face
是真正的字重 700 的字体，任何应用匹配到它都不会再走自己的假粗逻辑。

用法::

    boldgen scan                 # 看看哪些中文字体家族缺粗体
    boldgen interactive          # 交互式勾选并生成
    boldgen generate --family 宋体 --family 黑体
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
