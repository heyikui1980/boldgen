# 贡献指南

感谢你愿意为 `boldgen` 出力。这个项目很小，规则也不多，但有几条是**硬性的**，
请先读一读。

---

## 一条硬规则：**不要提交字体文件**

本仓库**不包含任何字体文件**。

* `.gitignore` 已经挡住 `*.ttf` / `*.ttc` / `*.otf` / `*.otc`；
* 如果你的 PR 里带了字体文件，CI 会直接失败，PR 也会被要求修改。

原因：宋体、黑体、楷体、仿宋、方正系列、华文系列等字体是** proprietary** 的，
它们的**衍生作品**同样受原授权约束。把它们提交进仓库等于再分发。

测试需要字体怎么办？用 `tests/conftest.py` 里的**内置 writer 现场构造**最小
TrueType 字体——`make_font_bytes()` 没有任何外部依赖，在任何机器上结果都一致。

---

## 开发环境

```bash
git clone https://github.com/<你的 fork>/boldgen.git
cd boldgen
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`dev` extra 包含 `pytest` 和 `build`。运行测试：

```bash
.venv/bin/python -m pytest -q
```

> **提示**：如果 `pip install -e .` 失败（某些发行版的 venv 里没有 setuptools），
> 可以不装本项目，直接跑测试——`pyproject.toml` 里配了
> `pythonpath = ["src", "tests"]`：
>
> ```bash
> .venv/bin/python -m pytest -q
> ```

---

## 代码风格

没有强制跑 black/ruff（保持零依赖），但请遵循现有代码的约定：

* **类型标注齐全**，函数签名都有；
* **docstring 用中文**，说明「为什么这么做」而不只是「做了什么」；
* **注释解释陷阱**，例如：

  ```python
  # fsSelection 在 OS/2 v0 里同样位于偏移 62，不需要按版本区分
  ```

* 单个函数别太长。`geometry.py` 是核心引擎，里面每个公开函数都该有测试。

---

## 提交信息

* 用中文或英文都行，保持一致即可；
* 首个词用祈使句动词：`fix:` / `feat:` / `docs:` / `test:` / `refactor:`；
* 一行摘要 + 空行 + 正文。正文说明**为什么**，不只说改了什么。

---

## 提交 PR 之前

必须通过：

```bash
.venv/bin/python -m pytest -q          # 全部测试通过
.venv/bin/python -m build              # 能打出 sdist + wheel
```

CI（`.github/workflows/ci.yml`）跑的就是这两件事。

---

## 值得贡献的方向

按难度从低到高：

| 方向 | 说明 |
|---|---|
| **CFF / OTF 轮廓支持** | 现在只处理 TrueType（`glyf` 表）。CFF 轮廓的膨胀算法完全不同（`cubic` 曲线偏移），是最大的功能缺口。见 `builder.py` 里的 `UnsupportedFontError`。 |
| **OpenType 布局表校正** | 现在 `GDEF` / `GSUB` / `GPOS` 原样保留。加粗后部分字距会不准（尤其是标点挤压类规则），可以加上针对度量变化的校正。 |
| **可变字体（Variable Font）** | `gvar` / `HVAR` / `avar` 的处理。 |
| **更好的别名目标推荐** | `alias.py` 里的打分逻辑目前比较粗糙，可以加入「字形风格相似度」（衬线/无衬线/楷/仿宋）判断。 |
| **Windows / macOS 支持** | 目前只验证过 Linux + fontconfig。 |
| **更多 CJK 判定方式** | `cjk.py` 目前用 `fc-list` 的 charset 覆盖 + 家族名判断，可以加入 Unicode 区块统计。 |

---

## 关于测试的约定

* **测试不依赖外部字体文件**——用 `make_font_bytes()` 构造；
* 几何相关的改动**必须**有对应的回归测试（面积变大/内孔变小/尖刺长度有界）；
* 生成产物的改动**必须**验证 `verify_font()` 通过；
* 新增的 `glyf` 表字段要有解析与写回的往返（round-trip）测试。

---

## 提交 issue

* **bug**：请附上 `boldgen --version`、系统版本、字体文件（**如果是 proprietary 字体，
  请只描述现象，不要附文件**）、以及 `boldgen scan --json` 的输出；
* **功能请求**：先开 issue 讨论，不要直接开 PR——尤其是涉及授权边界的问题
  （见 [`docs/licensing.zh.md`](docs/licensing.zh.md)）。

---

## 授权问题请先读文档

本项目**只分发代码**。生成物的授权由**源字体**决定。
如果你打算贡献与字体再分发相关的功能（比如打包字体数据库、下载字体等），
请先读 [`docs/licensing.zh.md`](docs/licensing.zh.md)，
并在 PR 里明确说明该功能是否符合上述边界。

---

## 联系

* 讨论与提问：GitHub Issues
* 报告 WPS 的渲染 bug：见 [`docs/upstream/wps-issue.zh.md`](docs/upstream/wps-issue.zh.md)
