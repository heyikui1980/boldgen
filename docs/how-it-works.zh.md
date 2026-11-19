# 原理：轮廓外扩算法与 WPS 黑块 bug 的证据链

本文分两部分：

1. [合成粗体的几何算法](#一合成粗体的几何算法)——`boldgen` 到底做了什么；
2. [WPS 中文加粗黑块的完整证据链](#二wps-中文加粗黑块的完整证据链)——为什么问题出在应用而不是字体。

---

## 一、合成粗体的几何算法

### 1.1 TrueType 轮廓的基本约定

* 坐标系 y 轴向上；
* **外轮廓按顺时针排列**，**内孔按逆时针排列**；
* 填充规则是 non-zero winding；
* 两个**连续**的 off-curve 控制点之间隐含一个 on-curve 点，位置是这两点的中点。

沿轮廓方向的切线 `t` 旋转 90° 得到法线 `rot90(t) = (-t.y, t.x)`。
由于外轮廓顺时针、内孔逆时针，这个法线**对两类轮廓都指向远离填充区域的一侧**。
所以"沿法线外扩 `r`"这个操作，对外轮廓就是**向外膨胀**，对内孔就是**向内收缩**——
两者都让笔画变粗。这就是 `geometry.py` 里只用一个法线公式就能同时处理
外轮廓和内孔的原因。

### 1.2 偏移一个点

给定一个顶点 `p`、入向切线 `t_in`、出向切线 `t_out`、半径 `r`：

```
n1 = rot90(t_in)        n2 = rot90(t_out)
m  = n1 + n2             角平分方向
cos(θ/2) = m̂ · n1       θ 是两法线的夹角
斜接长度 = r / cos(θ/2)
```

三种情况：

| 情况 | 处理 | 理由 |
|---|---|---|
| `cos(θ/2) <= 0` | **斜切（bevel）**：插入 `p + n1·r` 和 `p + n2·r` 两个点 | 两法线几乎相反 = 轮廓折返，斜接长度发散 |
| 斜接长度 > `r × miter_limit` | **斜切** | SVG / PostScript 的标准行为 |
| 其余 | **斜接**：插入一个点 | 常规拐角 |

**斜切是关键修正。** 早期实现在"斜接失败"时把长度**钳到上限**，
于是在凹角留下一根 `miter_limit`（默认 4）倍半径的长尖刺——
这是合成粗体最主要的伪影来源，也是"WPS 的粗体看起来像被抹开"的同类问题。

> 回归测试：`tests/test_geometry.py::test_embolden_no_long_spikes`
> 断言偏移后没有任何点离原轮廓超过 `1.5r`。

### 1.3 隐含中点的物化

TrueType 里两个连续 off-curve 点之间的 on-curve 中点**并不以显式点存在**。
读取时必须按规则补出来（`geometry.resolve()`）。

加粗时这个中点很重要：它决定拐角处接缝的位置。如果只是把中点"算出来用一下"
却不写回文件，写出的轮廓里两个控制点之间的中点位置就会漂移，
拐角处会出现细微的错位。

`boldgen` 默认把隐含中点**物化**成显式点再写出（`materialize=True`），
几何更准，代价是文件略大。用 `--no-materialize` 可以关掉。

### 1.4 复合字形

复合字形（由其它字形拼成，例如带撇捺的汉字、或拉丁字母的连字）
**不做整体加粗**。理由：

* 复合字形的分量本身也是字形表里的条目，它们会被各自加粗，合成后自动继承效果；
* 如果对复合字形整体做轮廓偏移，等于把分量**再叠加**一次偏移，笔画会粗两倍。

代价是：分量若带缩放，其笔画粗细会随缩放变化。

### 1.5 写出时的表处理

生成一个 Bold face 时：

| 表 | 处理 |
|---|---|
| `glyf` / `loca` | 重建（loca 统一用 long 格式） |
| `head` | `macStyle` 置 bold 位；`indexToLocFormat` = 1 |
| `OS/2` | `usWeightClass` = 700；`fsSelection` 置 BOLD、**清** REGULAR；PANOSE Weight = 8 |
| `name` | nameID 2 → `Bold`；3 → `<family>:Bold`；4 → `<family> Bold`；6 → `<psname>-Bold`；17 → `Bold` |
| `fpgm` `prep` `cvt ` | **剥掉**——旧 hinting 会把加粗后的笔画又削细 |
| `EBDT` `EBLC` | **剥掉**——内嵌位图是没加粗的 |
| `DSIG` | **剥掉**——改过字体后签名即失效 |
| `cmap` `hmtx` `maxp` `GSUB` `GDEF` `post` … | 原样保留 |

**nameID 2 必须是英文 `Bold`。**
它是 fontconfig 和绝大多数应用判断"这是粗体"的依据；写成"粗体"会破坏匹配。
真实的 Windows / macOS 字体在这一点上也一律使用英文样式名。
（各语言环境的样式名走 nameID 16/17 的排版族名，不影响匹配。）

### 1.6 校验和

按 OpenType 规范：

* 每张表的 `checkSum` = 表数据按 4 字节大端整数求和（末尾补零），模 2³²；
* `head` 的**目录校验和**按 `checkSumAdjustment = 0` 计算
  （真实字体也都是这么做的，已对 DejaVuSans.ttf / LiberationMono-Bold.ttf / simsun.ttc 逐一核对）；
* `head.checkSumAdjustment = 0xB1B0AFBA − (全文校验和，把该字段置零后计算)`。

---

## 二、WPS 中文加粗黑块的完整证据链

### 2.1 现象

Linux + WPS Office 的 Writer 里，任何**只有 Regular 字重**的中文字体，
一旦设为加粗，渲染成一团涂抹状的黑块。

### 2.2 排除项

| 假设 | 怎么排除的 | 结论 |
|---|---|---|
| 字体文件损坏 | 同一批字体在 Chrome 里加粗完全正常 | ✗ |
| fontconfig 配置错误 | 同一台机器、同一个 fontconfig，Chrome 正常 WPS 不正常 | ✗ |
| `unitsPerEm = 256` 太小 | 专门构造 `upem=1000` / `upem=1024` 的对照字体，同样黑块 | ✗ |
| FreeType 本身的问题 | Chrome 用的是 FreeType/Skia 的官方路径，渲染正确 | ✗ |
| 字号太小 | 32pt 一样黑块 | ✗ |
| 缺字 / fallback | 字形轮廓完整可见，只是被"撑胖"了 | ✗ |

### 2.3 定位到应用内部

WPS 的可执行文件在 `/opt/kingsoft/wps-office/office6/`，
Writer 的渲染器是 `libkso.so`。

用 `LD_PRELOAD` 做 spy，观察它对 FreeType 的调用：

* 有 `FT_Load_Glyph` / `FT_MulFix`；
* **没有** `FT_Outline_Embolden`。

也就是说，WPS 没有用 FreeType 官方的合成粗体，而是自己实现了一套轮廓加粗。
WPS 自己实现的那一套，把笔画放大了数倍。

### 2.4 量化

用控制多边形面积作墨量的无依赖代理，测量"粗体墨量 / 常规墨量"：

| 情形 | 墨量比 |
|---|---|
| Chrome（Skia + fontconfig `embolden`）的假粗 | 1.2 – 1.5 |
| FreeType `FT_Outline_Embolden` 的假粗 | ~1.8 |
| **本工具烘焙的粗体** | **1.85** |
| **WPS 出 bug 时** | **2.3 – 10.2** |

字形越密，WPS 的误差被放大得越厉害：

| 字 | WPS 出 bug 时的墨量比 |
|---|---|
| 中 | 2.3 |
| 贏 / 羸 / 鬱 | 6 – 8 |
| 鬥 / 齪 / 龘 | 9 – 10 |

### 2.5 结论

**只要 fontconfig 能匹配到一个真实的 Bold face，应用就不需要自己去合成，
bug 也就绕过去了。**

这正是 `boldgen` 的思路：与其去修每一个应用的合成粗体实现，
不如让缺粗体的家族**有**粗体。

### 2.6 为什么不是只针对 WPS

* WPS Writer 的 `libkso.so` —— 已确认。
* 其它应用可能有类似问题（各家都自己实现合成粗体，质量参差不齐）。
* 有真粗体的家族不受影响——这也是为什么 `boldgen` 默认**只处理缺粗体的家族**，
  不去覆盖已有的好字体。

---

## 三、参考资料

* FreeType `FT_Outline_Embolden` 源码：
  <https://gitlab.freedesktop.org/freetype/freetype/-/blob/master/src/base/ftoutln.c>
* OpenType 规范（`head` / `OS/2` / `name` / `glyf` / 校验和）：
  <https://learn.microsoft.com/typography/opentype/spec/>
* fontconfig 权重刻度（`%{weight}` 是缩放刻度，Bold=200 而不是 CSS 的 700）：
  <https://www.freedesktop.org/software/fontconfig/spec/>
