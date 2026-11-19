# 给 WPS 提交 issue 的材料

本文档汇总了向 WPS 官方（`wps.cn` / GitHub `kingsoft` 相关仓库）报告
「中文字体加粗被渲染成涂抹状黑块」这个问题所需的全部材料。

> **注意**：`boldgen` 是一个**绕行方案**，不是 WPS 的补丁。
> 本文档的目的是：即使你用 `boldgen` 绕过了问题，
> 根因仍然值得报告给 WPS——**同一个 bug 会影响所有只有 Regular 字重的字体**，
> 而不只是中文。

---

## 一、给 issue 的正文模板

复制下面这段，填好方括号里的内容，提交到 WPS 的反馈渠道
（[WPS 反馈中心](https://www.wps.cn/feedback/)、Linux 版社区论坛、
或 GitHub 上对应的 issue 跟踪仓库）。

```markdown
### 问题描述

在 Linux 版 WPS Writer 中，把**只有 Regular 一个字重**的中文字体设置为加粗时，
中文会被渲染成一团**涂抹状的黑块**（笔画互相糊在一起，无法辨认），
而同一份文档在 Google Chrome / Firefox / LibreOffice 中显示正常。

受影响字体举例：宋体(SimSun)、黑体(SimHei)、楷体(KaiTi)、仿宋(FangSong)、
方正系列、华文系列。

### 复现步骤

1. 确认系统里安装的字体只有 Regular 字重：
   ```bash
   fc-list | grep -i simsun
   # 预期只出现 "SimSun:style=Regular"，没有 Bold
   ```
2. 在 WPS Writer 新建文档，输入任意中文，例如「中文加粗测试」。
3. 选中文字，Ctrl+B 加粗（或在字体设置里选「加粗」）。
4. 文字变成涂抹状黑块。

### 对照实验

同一份文档用以下方式打开，加粗中文显示**完全正常**：

- Google Chrome（Skia + fontconfig `embolden`）
- LibreOffice Writer

### 预期结果

加粗后的中文应当是笔画略粗、清晰可辨的文本。

### 实际结果

笔画被放大数倍，互相重叠成一团黑。

### 补充信息

- WPS 版本：<在 WPS 里「关于」里看，Linux 版请注明是 AUR 的哪个包>
- 发行版：<如 Ubuntu 24.04.5>
- 桌面环境：<如 GNOME 46>
- 字体版本：<如 SimSun 版本 5.00/2023/06/22>

### 附：最小复现文件

请附上 `boldgen mktest` 生成的 docx（见下文），它对每个字体输出
「加粗行 + 常规行」两行，方便一眼看出问题。

同时附上字体文件本身（**注意**：`SimSun` 等微软字体受版权约束，
如不便附上，请使用开源中文字体复现，例如只有 Regular 字重的
文泉驿正黑 / AR PL UKai / Droid Sans Fallback）。
```

---

## 二、为什么这个 bug 值得报

三句话说清楚：

1. **WPS 的 Writer 渲染器自己实现了轮廓加粗**（在 `libkso.so` 里），
   而不是用 FreeType 官方的 `FT_Outline_Embolden`。
2. 它的实现把笔画放大得**远超合理范围**——实测墨量达到常规字体的
   **2.3×–10.2×**，而正常的合成粗体应该在 **1.2×–1.5×**。
3. 这套实现**只在字体没有真 Bold face 时才会被触发**，
   所以「装一个带真粗体的字体」就能绕开——但 WPS 本身应该把这件事做好。

完整的证据链（`LD_PRELOAD` 挂钩记录、墨量测量方法、可复现的测量脚本）
见 [`../how-it-works.zh.md`](../how-it-works.zh.md)。

---

## 三、最小复现文件的生成方法

`boldgen mktest` 会生成一个纯手写 XML 的 `.docx`（不依赖任何第三方库），
每个字体两行：

```
[SimSun BOLD]中文加粗测试
[SimSun reg ]中文加粗测试
```

```bash
# 生成默认样本（宋体/黑体/楷体/仿宋）
boldgen mktest --out /tmp/bold-test.docx

# 指定字体
boldgen mktest --out /tmp/bold-test.docx \
    --font 宋体 --font 黑体 --font KaiTi

# 自定义样本文本
boldgen mktest --out /tmp/bold-test.docx --sample 中文加粗测试abc
```

生成的文件可以直接打开来看；**如果加粗行变成黑块而常规行正常，
就说明复现成功**。

---

## 四、给字体作者的临时建议

如果你不方便提交 issue，可以用下面任一方式绕开：

1. **给字体加一个真 Bold face**——就是 `boldgen` 做的事（见项目 README）；
2. **在 fontconfig 里把加粗请求映射到已有的粗体**——`boldgen alias` 模式；
3. **在 WPS 里改用有粗体的替代字体**——例如宋体 → Noto Serif CJK SC。
