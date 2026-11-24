# boldgen — 给缺粗体的字体家族烘焙真正的 Bold

[![CI](https://github.com/heyikui1980/boldgen/actions/workflows/ci.yml/badge.svg)](https://github.com/heyikui1980/boldgen/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/heyikui1980/boldgen/blob/main/LICENSE)

**Linux 上的 WPS（以及其它合成粗体实现有问题的应用）会把中文加粗渲染成一团涂抹状黑块。**
`boldgen` 为**缺少粗体的字体家族**离线烘焙出真正的 Bold 字体文件，
让所有应用都能匹配到一个货真价实的粗体，而不是让应用自己去"假粗"。

```
$ boldgen scan --missing-bold
共 73 个字体家族（仅中文字体）：

家族                                                          状态    中文  源文件
------------------------------------------------------------  ------  ----  ---------------------------------------------------------------
AR PL UKai CN                                                 缺粗体  是    /usr/share/fonts/truetype/arphic/ukai.ttc#0
AR PL UKai HK                                                 缺粗体  是    /usr/share/fonts/truetype/arphic/ukai.ttc#1
AR PL UKai TW                                                 缺粗体  是    /usr/share/fonts/truetype/arphic/ukai.ttc#2
AR PL UKai TW MBE                                             缺粗体  是    /usr/share/fonts/truetype/arphic/ukai.ttc#3
...

$ boldgen generate --family 宋体 --family 黑体
✓ 生成 2 个粗体 face：
    SimSun    SimSun-Bold.ttf  字形 28862  半径 4  10.1 MB
    SimHei    SimHei-Bold.ttf  字形 28562  半径 4  10.0 MB
  合计 20.1 MB
  已安装到 /home/you/.local/share/fonts/boldgen
  fontconfig 缓存已刷新
```

---

## 目录

- [问题是什么](#问题是什么)
- [为什么不是 WPS 的锅，也不是字体的锅](#为什么不是-wps-的锅也不是字体的锅)
- [boldgen 做什么](#boldgen-做什么)
- [两种处理方式](#两种处理方式)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令一览](#命令一览)
- [验证效果](#验证效果)
- [它不会做什么](#它不会做什么)
- [已知限制](#已知限制)
- [授权](#授权)
- [文档](#文档)
- [English](https://github.com/heyikui1980/boldgen/blob/main/README.en.md)

---

## 问题是什么

在 Linux 上用 WPS Writer 打开中文文档，把任何一段中文设为**加粗**：

| 字体 | 常规 | 加粗 |
|---|---|---|
| SimSun（宋体） | 正常 | **一团黑块** |
| SimHei（黑体） | 正常 | **一团黑块** |
| KaiTi（楷体） | 正常 | **一团黑块** |
| Noto Sans CJK SC | 正常 | 正常（它本来就有真粗体） |

规律很干脆：**这个家族没有真正的 Bold face 时，加粗就会变成黑块**。

## 为什么不是 WPS 的锅，也不是字体的锅

排查下来是这样的：

1. **不是字体文件坏了。** 同一批字体在 Chrome（Skia + fontconfig `embolden`）里加粗完全正常。
2. **不是 fontconfig 配置的问题。** 同一台机器、同一个 fontconfig，Chrome 正常、WPS 不正常。
3. **不是 `unitsPerEm` 的问题。** 专门构造 `upem=1000/1024` 的对照组，同样黑块。
4. **是 WPS 自己的合成粗体实现有 bug。**
   WPS Writer 的渲染器（`libkso.so`）只调用 `FT_Load_Glyph` / `FT_MulFix`，
   **没有**调用 FreeType 官方的 `FT_Outline_Embolden`，
   而是自己实现了一套轮廓外扩——放大了好几倍。

实测粗体墨量（相对常规字重的倍数）：

| | 正常假粗 | 本工具烘焙的粗体 | WPS 出 bug 时 |
|---|---|---|---|
| 墨量倍数 | 1.2 – 1.5 | **1.85** | **2.3 – 10.2** |

> 完整证据链见 [`docs/how-it-works.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/how-it-works.zh.md)。

**所以真正的解法不是"修 WPS"，而是"让这些家族有真正的粗体"。**
一旦 fontconfig 能匹配到一个真实的 Bold face，应用根本不需要自己去合成，
WPS 的 bug 就绕过去了——而且不止 WPS，别的应用也一并受益。

## boldgen 做什么

对系统里**缺粗体**的字体家族：

1. 扫描 fontconfig，把字体按家族分组，识别出哪些家族没有真粗体；
2. 挑出该家族的常规字重 face 作为源；
3. 把每个字形的轮廓**向外偏移**（真正的几何外扩，不是"加粗滤镜"），
   写出成一个带完整元数据（`name` / `OS/2` / `head`）的全新 Bold 字体文件；
4. 装到 `~/.local/share/fonts/boldgen/`（用户级，无需 sudo），刷新 fontconfig 缓存。

字形本身**完全不变**，只是笔画变粗——和 FreeType / Skia 做的合成粗体是同一类操作，
但用的是经过验证的几何实现（见下）。

### 几何实现

和 FreeType 的 `FT_Outline_Embolden` 思路一致，但修掉了两个常见问题：

- **斜接失败退化为斜切（bevel）**，而不是把斜接长度钳到上限——
  后者会在凹角留下一根 4 倍半径的长尖刺，是合成粗体最主要的伪影来源。
- **隐含 on-curve 中点物化**为显式点，让拐角处的接缝几何精确。

## 两种处理方式

`boldgen interactive` 里用单选切换：

| | 合成粗体生成器 | fontconfig 别名 |
|---|---|---|
| 做什么 | 离线烘焙出真正的 Bold 字体文件 | 把"该家族 + 加粗"的请求重定向到另一个已有粗体的家族 |
| 字形 | **保持原样**，只是变粗 | **变成目标字体的** |
| 磁盘 | 每个家族多一份（中文大字体几十 MB） | 零 |
| 适用范围 | 任何应用 | 只认 fontconfig 的应用 |
| 撤销 | `boldgen uninstall` | 删掉一条配置文件 |

**默认用生成器模式。** 别名模式在磁盘紧张、或者只是临时顶一下的时候有用。

## 安装

```bash
pipx install "git+https://github.com/heyikui1980/boldgen"   # 从源码
```

或者克隆下来本地装：

```bash
git clone https://github.com/heyikui1980/boldgen
cd boldgen
pipx install .
```

零必需依赖，纯 Python 3.9+ 标准库实现。想额外装 `fonttools` 做交叉验证：

```bash
pipx install "boldgen[ft] @ git+https://github.com/heyikui1980/boldgen"
```

> **PyPI 版本尚未发布。** 上线后就能直接 `pipx install boldgen`；
> 在此之前请用上面的源码安装方式。

> **CFF/OTF 轮廓**（`.otf`）目前**不支持**——内置引擎只处理 TrueType（`glyf`）轮廓。
> 遇到这类字体会明确报错，不会静默产出坏文件。

## 快速开始

```bash
# 1. 看看哪些中文字体缺粗体
boldgen scan
boldgen scan --missing-bold        # 只看缺粗体的
boldgen scan --json                # 机器可读

# 2. 交互式：勾选家族 → 选处理方式 → 确认参数 → 执行
boldgen interactive

# 3. 或者直接点名
boldgen generate --family 宋体 --family 黑体 --family 楷体

# 4. 确认装了什么
boldgen list
boldgen check          # 源字体变了会提示产物过期；也会检查加粗请求有没有被 fontconfig 劫持

# 5. 撤销
boldgen uninstall --family 宋体
boldgen uninstall --all
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `boldgen scan` | 扫描系统字体，列出家族及是否缺粗体 |
| `boldgen interactive` | **主入口**：扫描 → 勾选 → 单选处理方式 → 执行 |
| `boldgen generate` | 为指定家族生成粗体 face |
| `boldgen alias` | fontconfig 别名模式（列出 / 写入 / 删除规则） |
| `boldgen list` | 列出已安装的产物 |
| `boldgen check` | 检测源字体变化导致的产物过期；并检查加粗请求是否真的命中产物 |
| `boldgen uninstall` | 移除已安装的产物 |
| `boldgen mktest` | 生成用于人工验证的 `.docx` 测试文档 |

完整参数见 [`docs/cli.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/cli.zh.md)。

## 验证效果

**渲染结果**才是唯一可靠的验收标准，所以工具自带一个测试文档生成器：

```bash
boldgen mktest --out /tmp/t.docx --open
```

生成的文档里每个字体两行——一行加粗、一行常规——
用 WPS / LibreOffice 打开，加粗行应该是正常的粗体，而不是黑块。

## 它不会做什么

- **不会**修改、覆盖或删除任何系统字体文件。产物只写在 `~/.local/share/fonts/boldgen/`，
  卸载就是删掉这个目录。
- **不会**改动 `~/.config/fontconfig/fonts.conf`。
  别名模式只写一个独立的文件 `~/.config/fontconfig/conf.d/99-boldgen-aliases.conf`，
  删掉它就完全还原。
- **不会**替你下载任何字体，也不联网。
- **不会**分发任何字体文件（见[授权](#授权)）。

## 已知限制

- **只支持 TrueType（`glyf`）轮廓。** CFF/OTF 暂不支持。
- **复合字形不做整体加粗。** 复合字形（由其它字形拼成）的分量字形各自加粗后
  自动继承效果；但如果分量被缩放，笔画粗细会跟着缩放变化。
- **坐标量化到整数字体单位。** `unitsPerEm=256` 的字体（宋体等）最小步长是 1/256 em，
  加粗半径 `round(256 × 0.015) = 4`。
- **变量字体只处理默认实例**，不做可变轴插值。
- **合成粗体永远比不上真粗体。** 烘焙出来的粗体在字形设计上没有经过设计师的打磨，
  但它至少是**正常显示的粗体**，而不是黑块。

## 授权

**软件本身**用 MIT 协议，见 [`LICENSE`](https://github.com/heyikui1980/boldgen/blob/main/LICENSE)。

**生成的字体文件不随本项目分发**，它们继承源字体的授权：

| 字体 | 可否再分发衍生作品 |
|---|---|
| SimSun / SimHei / KaiTi / FangSong（微软） | ✗ |
| 方正系列 / 华文系列 / ST 系列 | ✗ |
| Noto / 思源 / 文泉驿 / 文鼎 | 按各自授权 |
| DejaVu / Liberation 等 | 按各自授权 |

> 详见 [`docs/licensing.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/licensing.zh.md) 与 [`NOTICE`](https://github.com/heyikui1980/boldgen/blob/main/NOTICE)。

本项目**只分发代码**。请在你自己的机器上生成衍生字体，并遵守源字体的授权条款。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/how-it-works.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/how-it-works.zh.md) | 轮廓外扩算法 + WPS bug 的完整证据链 |
| [`docs/cli.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/cli.zh.md) | 每个子命令的完整参数说明 |
| [`docs/licensing.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/licensing.zh.md) | 各类字体的授权与可再分发性对照表 |
| [`docs/upstream/wps-issue.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/upstream/wps-issue.zh.md) | 给 WPS 的 issue 模板 + 最小复现步骤 |
| [`docs/publishing.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/publishing.zh.md) | 维护者向：发布到 PyPI 的完整流程 |

## 参与贡献

见 [`CONTRIBUTING.md`](https://github.com/heyikui1980/boldgen/blob/main/CONTRIBUTING.md)。

## License

[MIT](https://github.com/heyikui1980/boldgen/blob/main/LICENSE) — 但请先读 [`NOTICE`](https://github.com/heyikui1980/boldgen/blob/main/NOTICE)。
