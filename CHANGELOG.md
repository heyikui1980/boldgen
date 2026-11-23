# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 修复

- **`boldgen check` 的 fontconfig 命中检查现在会转义家族名**。
  fontconfig 的模式解析器（`FcNameParse`）会把家族名里**第一个连字符之后的
  整段**当成"样式后缀"丢掉——`fc-pattern "FZFangSong-Z02"` 解析出来是
  `family="FZFangSong"`，于是 `fc-match "FZFangSong-Z02"` 会**静默**匹配失败
  并回落到 sans-serif。不转义的话，这类家族名会被误报成"加粗请求被劫持"。
  新增 `boldgen.discover.escape_pattern()`。
- 命中检查现在会把一个家族**所有的名字**（英文名 + 中文名）都查一遍，
  而不是只查主名。
- 区分两种"没命中"：
  - 只有加粗被劫持 → ⚠ 警告（本工具需要提醒的问题）；
  - 常规字重也被劫持 → ℹ 提示（fontconfig 里本来就有的 strong 别名，与产物无关）。
- `boldgen check` 新增 `--no-fc-check`，可跳过 fontconfig 命中检查。
- `boldgen generate` 支持源字体是 `.ttc` 的第 N 个 face（此前会误报
  "非 TTC 文件只能取 face 0"）。
- 报告表格按**显示宽度**对齐，中文列不再歪。

## [0.1.0] — 2026-11-19

首个版本。

### 核心引擎

- **零依赖的 TrueType 轮廓外扩算法**（`geometry.py`）
  - 按 TrueType 绕向约定（外轮廓顺时针、内孔逆时针）向外膨胀：
    外轮廓变大、内孔变小；
  - 斜接（miter）长度上限 `r * miter_limit`，超限退化为**斜切（bevel）**——
    这一条修掉了旧实现里凹角处产生 4 倍半径长尖刺的伪影；
  - 隐含 on-curve 中点**物化为显式点**，保证写出后中点仍是两个控制点的中点。
- **sfnt 容器读写**（`sfnt.py`）
  - 支持 TrueType Collection（`.ttc`）的指定 face；
  - `name` 表按平台正确编码（pid 0/3 → UTF-16BE，pid 1 → MacRoman），
    中文名不再退化成 `?`；
  - 重算每张表的 `checkSum` 与 `head.checkSumAdjustment`（`head` 的目录校验和
    按规范以 `checkSumAdjustment = 0` 计算）。
- **glyf 表解析/序列化**（`glyf.py`），复合字形原样保留。
- **粗体 face 构建**（`builder.py`）
  - 更新 `OS/2.usWeightClass`（700）、`fsSelection` 的 BOLD 位、
    PANOSE 字重、`head.macStyle`；
  - 剥掉不再适用的表：`fpgm` / `prep` / `cvt `（旧 hinting 会把加粗后的笔画
    又削细）、`EBDT` / `EBLC`（未加粗的位图）、`DSIG`（签名已失效）；
  - 在 `name` 表 nameID 5 写入修改声明（满足 Arphic Public License 的
    「在每个修改过的文件里插入显著的修改声明」要求）。
- **产物自检**（`verify.py`）：字重、macStyle、字形可解析性、墨量比回归。

### 扫描与安装

- `boldgen scan`：调用 `fc-list` 扫描系统字体，按家族分组，
  标出**缺少真粗体**的家族（已用 fontconfig 的缩放刻度判定：
  Bold = 200，不是 CSS 的 700）。
- `boldgen cjk` 判定：家族名含 CJK 字符，或 charset 覆盖 U+4E00–U+9FA5。
- `boldgen generate`：为指定家族生成粗体并安装到
  `~/.local/share/fonts/boldgen/`，附 `manifest.json`（记录源文件 sha256）。
- `boldgen list` / `check` / `uninstall`：安装管理，`check` 用源文件哈希
  检测产物是否过期。

### fontconfig 别名模式

- `boldgen alias`：把「某家族 + 加粗」的请求映射到已有的粗体，
  规则写入 `~/.config/fontconfig/conf.d/99-boldgen-aliases.conf`。
  零体积，但字形会变成目标字体的样子。
- 别名目标**自动推荐**：按衬线/无衬线/楷/仿宋类别、是否真有粗体、
  CJK 覆盖度打分。

### 交互式界面

- `boldgen interactive`：扫描 → 勾选家族 → **单选**处理方式
  （生成器 / 别名）→ 参数确认 → 执行计划预览 → 执行。
- 非 TTY 环境自动退化为逐行输入。
- 过滤只影响显示，不影响已勾选状态；`a` / `n`（全选 / 全不选）针对**全部**家族，
  不受过滤影响。

### 验证辅助

- `boldgen mktest`：生成纯手写 XML 的 `.docx`（无第三方依赖），
  每个字体输出「加粗行 + 常规行」两行，用于在 WPS 里肉眼验证。

### 文档

- `README.md` / `README.en.md`：问题现象 → 根因 → 快速开始 → 两种模式对比。
- `docs/how-it-works.zh.md`：轮廓外扩算法 + WPS bug 的完整证据链。
- `docs/cli.zh.md`：完整 CLI 参数说明。
- `docs/licensing.zh.md`：各类字体的授权与可再分发性对照表。
- `docs/upstream/wps-issue.zh.md`：给 WPS 的 issue 模板与最小复现步骤。

### 测试

- 177 个测试，全部用内置 writer 现场构造字体，**不依赖任何外部字体文件**，
  在任何机器上结果一致。

### 已知限制

- 只支持 TrueType 轮廓（`glyf`）；CFF/OTF 会明确报错。
- 复合字形不做整体加粗（其分量字形各自加粗后自动继承效果）。
- 被缩放的复合分量，其笔画粗细会随缩放变化。
- 坐标量化到整数字体单位（upem 256 时即 1/256 em）。

[未发布]: https://github.com/heyikui1980/boldgen/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/heyikui1980/boldgen/releases/tag/v0.1.0
