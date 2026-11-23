# 命令行参考

`boldgen` 有 8 个子命令。所有涉及安装的子命令都支持 `--install-dir`，
默认是 `~/.local/share/fonts/boldgen/`（用户级，不需要 sudo）。

```bash
boldgen --help          # 总览
boldgen <命令> --help    # 单个命令的参数
```

---

## 全局约定

### 安装目录

| 变量 | 默认值 | 说明 |
|---|---|---|
| `--install-dir` | `~/.local/share/fonts/boldgen/` | 产物落盘目录 |

这个目录是 Linux 上**不需要 sudo** 就能让 fontconfig 看到新字体的位置
（`~/.fonts` 在现代发行版上已不再被默认扫描）。
同一目录下的 `manifest.json` 记录每个产物的来源、参数与校验和。

### 字体家族名怎么写

`--family` 接受**主名或任意别名**，中英文都行，大小写不敏感：

```bash
boldgen generate --family 宋体      # ✓ 别名
boldgen generate --family SimSun    # ✓ 主名
boldgen generate --family simsun    # ✓ 大小写不敏感
```

先用 `boldgen scan` 看看有哪些名字可用。

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 部分失败（例如某个家族生成失败、或 `check` 发现过期产物） |
| 2 | 参数错误（例如 `--family` 找不到对应的家族） |
| 130 | 被 Ctrl-C 中断 |

---

## `boldgen scan`

扫描系统字体，按家族分组，标出哪些家族**缺少真正的粗体**。

```bash
boldgen scan                  # 只看中文字体
boldgen scan --all            # 所有字体
boldgen scan --missing-bold   # 只看缺粗体的
boldgen scan --json           # 机器可读
boldgen scan --exclude-dir /opt/fonts   # 排除某个目录（可重复）
```

输出示例：

```
共 51 个字体家族（仅中文字体）：

家族                    状态    中文  源文件
--------------------------------------------
AR PL UKai CN           缺粗体  是    /usr/share/fonts/truetype/arphic/ukai.ttc#0
LiSu (隶书)             缺粗体  是    /usr/share/fonts/truetype/winfonts/SIMLI.TTF
Noto Sans CJK SC        有粗体  是    /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
```

| 列 | 含义 |
|---|---|
| 家族 | 主名（附中文别名） |
| 状态 | `缺粗体` / `有粗体` |
| 中文 | 是否中文字体（覆盖汉字，或名字里有中日韩文字） |
| 源文件 | 建议用来合成的源 face，`.ttc` 用 `路径#序号` |

**JSON 结构**：

```json
[
  {
    "key": "SimSun",
    "names": ["SimSun", "宋体"],
    "is_cjk": true,
    "has_real_bold": false,
    "faces": [
      {
        "path": "/usr/share/fonts/custom/simsun.ttc",
        "index": 0,
        "style": "Regular",
        "weight": 80,
        "slant": 0,
        "location": "/usr/share/fonts/custom/simsun.ttc#0"
      }
    ]
  }
]
```

> `weight` 是 **fontconfig 的缩放刻度**，不是 CSS 的 100–900：
> Regular=80、Light=50、Medium=100、SemiBold=180、**Bold=200**、ExtraBold=205、Black=210。
> 判定粗体的门槛是 `>= 200`。

---

## `boldgen generate`

为指定家族生成粗体 face 并安装。

```bash
boldgen generate --family 宋体 --family 黑体
boldgen generate --family SimSun --strength 0.02
boldgen generate --family 宋体 --dry-run
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--family` | — | 字体家族名，可重复 |
| `--strength` | `0.015` | 加粗系数：外扩半径 = `round(unitsPerEm × 系数)` |
| `--weight` | `700` | 写入 `OS/2.usWeightClass` 的字重值 |
| `--suffix` | `Bold` | 样式名后缀（写进 `name` 表） |
| `--miter-limit` | `4.0` | 斜接长度上限倍数，超过退化为斜切 |
| `--no-materialize` | 关 | 不把隐含 on-curve 中点物化（文件更小，几何略有偏差） |
| `--all` | 关 | 允许处理非中文字体 |
| `--dry-run` | 关 | 只生成不安装 |
| `--install-dir` | `~/.local/share/fonts/boldgen/` | 安装目录 |
| `--exclude-dir` | — | 扫描时排除的目录（可重复） |

**关于 `--strength`**：半径是按 `unitsPerEm` 算的，所以不同字体天然可比。
但字体的 `unitsPerEm` 差异很大：

| 字体 | unitsPerEm | 半径（strength=0.015） |
|---|---|---|
| SimSun（宋体） | 256 | 4 |
| Noto Sans CJK | 1000 | 15 |

`round(256 × 0.015) = round(3.84) = 4`。
如果某个字体看起来加粗不够，把 `--strength` 调大一点试试
（宋体建议 `0.02` ~ `0.03`）。

**生成流程**：先写进临时目录，**逐个自检通过后才安装**——
自检不过（表校验和错、字形解析失败、墨量反而变小等）就不会留下坏文件。

---

## `boldgen list`

列出已安装的产物。

```bash
boldgen list
boldgen list --json
```

```
已安装 22 个粗体 face（/home/hyk/.local/share/fonts/boldgen）：

  FangSong                 FangSong-Bold.ttf                10.7 MB
      源: /usr/share/fonts/truetype/winfonts/simfang.ttf
  ...
```

---

## `boldgen check`

检测两件事：

1. 产物是否**过期**——即源字体在生成之后被改动过（升级、替换等）；
2. 加粗请求**是否真的落到了产物上**——被 fontconfig 的 `<alias binding="strong">`
   规则劫持的话，产物再完美也不会被用上，这是"装了却没效果"最常见的原因。

```bash
boldgen check
```

```
✓ 22 个产物都是最新的，且加粗请求都能命中。
```

```
⚠ 2 个产物已过期：
    SimSun（源文件已变化：/usr/share/fonts/custom/simsun.ttc）
⚠ 1 个文件缺失：
    SimHei-Bold.ttf
```

```
⚠ 1 个家族的加粗请求没有命中本工具的产物：
    SimSun → 命中 /usr/share/fonts/opentype/noto/NotoSans-Bold.ttf
    （Noto Sans / Bold），而不是 SimSun-Bold.ttf

  通常是 fontconfig 里有一条 <alias binding="strong"> 规则
  把这个家族名重定向到了别的字体。检查：
      grep -rn "<family>家族名</family>" ~/.config/fontconfig/ /etc/fonts/conf.d/
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--no-fc-check` | 关 | 跳过 fontconfig 命中检查（只查过期与缺失） |

退出码：有过期、缺失或加粗被劫持时返回 `1`。

### 关于 fontconfig 命中检查的几个坑

- **一个家族往往有多个名字**（英文名 + 中文名，如 `FZFangSong-Z02` 和 `方正仿宋_GBK`）。
  应用用哪个名字请求加粗是不确定的，所以 `check` 会把**每个**名字都查一遍。
- **连字符必须转义**。fontconfig 的模式解析器（`FcNameParse`）会把家族名里
  **第一个连字符之后的整段**当成"样式后缀"丢掉：

  ```
  $ fc-pattern "SimSun-Bold"
  Pattern has 1 elts (size 16)
      family: "SimSun"(s)
  ```

  也就是说 `fc-match "FZFangSong-Z02"` 会静默匹配失败并回落到 sans-serif。
  正确的写法是用反斜杠转义：`fc-match "FZFangSong\\-Z02"`。
  `boldgen` 内部会自动转义，你手敲 `fc-match` 时记得也要加。
- **常规字重也被劫持 vs 只有加粗被劫持**：如果连常规字重都被 strong 别名重定向了，
  说明是系统/用户本来就配了别名（比如把 `KaiTi` 指向 `AR PL UKai CN`），
  与本工具的产物无关，`check` 会把它归到"ℹ 提示"而不是"⚠ 警告"。

---

## `boldgen uninstall`

移除已安装的产物。**只删本工具生成的文件**，不会碰系统字体。

```bash
boldgen uninstall --family 宋体
boldgen uninstall --all
```

`--family` 接受家族名或产物文件名。删完会刷新 fontconfig 缓存。

---

## `boldgen mktest`

生成用于人工验证的 `.docx` 测试文档。

```bash
boldgen mktest --out /tmp/t.docx
boldgen mktest --out /tmp/t.docx --open      # 生成后用 WPS 打开
boldgen mktest --font SimSun --font SimHei
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--out` | `./boldgen-test.docx` | 输出路径 |
| `--font` | 已安装的家族 + 常见中文字体 | 要测试的字体名，可重复 |
| `--sample` | `中文加粗测试` | 中文样本文字 |
| `--size` | `24` | 字号（半磅），24 = 12pt |
| `--open` | 关 | 生成后调用 `wps` 打开 |

文档里每个字体**两行**：一行加粗、一行常规，左边用等宽 ASCII 标注家族名。
在 WPS 里打开，加粗行应该是正常的粗体。

---

## `boldgen interactive`

**主入口**：扫描 → 勾选 → 选处理方式 → 确认参数 → 执行。

```bash
boldgen interactive
```

### 勾选列表

| 按键 | 作用 |
|---|---|
| `空格` | 切换当前行 |
| `j` / `k` / `↓` / `↑` | 移动 |
| `a` | 全选（当前过滤结果内） |
| `n` | 全不选 |
| `/` | 按关键词过滤（回车应用，Esc 取消） |
| `Enter` | 下一步 |
| `q` | 取消 |

非 TTY 环境（管道、CI）下自动退化为"逐行输入序号"，不会挂起。

### 单选处理方式

```
── 选择处理方式 ──
 > (*) 合成粗体生成器
        离线生成真正的 Bold 字体文件，任何应用都能匹配到。效果最好，
        每个家族多占一份磁盘。
   ( ) fontconfig 别名
        把加粗请求重定向到另一个已有粗体的家族。零额外磁盘占用，
        但字形会变成目标字体的。
```

用 `空格` 或 `Enter` 选中当前项，`1` / `2` 直接选。

### 之后的流程

* **生成器模式**：询问加粗强度与字重 → 打印执行计划 → 确认 → 生成 → 安装 → `fc-cache`。
* **别名模式**：为每个家族推荐目标粗体（按衬线/无衬线/楷/仿宋类别打分）→
  打印规则 → 确认 → 写入 `~/.config/fontconfig/conf.d/99-boldgen-aliases.conf`。

| 参数 | 说明 |
|---|---|
| `--all` | 不限于中文字体 |
| `--include-has-bold` | 把已有粗体的家族也列进候选 |
| `--dry-run` | 只生成不安装 |
| `--target` | 别名模式下统一指定目标粗体家族 |
| `--install-dir` | 安装目录 |

---

## `boldgen alias`

fontconfig 别名模式：把"该家族 + 加粗"的请求重定向到另一个已有粗体的家族。

```bash
boldgen alias --list                                  # 列出已有规则
boldgen alias --family SimSun --target "Noto Serif CJK SC"
boldgen alias --all --dry-run                         # 预览
boldgen alias --remove --family SimSun                # 删除规则
boldgen alias --remove --all                          # 删除全部
```

生成的规则形如：

```xml
<match target="pattern">
  <test name="family" compare="eq"><string>SimSun</string></test>
  <test name="weight" compare="more_eq"><const>bold</const></test>
  <edit name="family" mode="assign"><string>Noto Serif CJK SC</string></edit>
</match>
```

只影响**加粗请求**；常规字重不受影响：

```bash
fc-match "宋体:bold"   # → NotoSerifCJK-Bold.ttc: "Noto Serif CJK SC" "Bold"
fc-match "宋体"        # → simsun.ttc: "SimSun" "Regular"   （不变）
```

> `<const>bold</const>` 会被 fontconfig 解析成缩放刻度上的 200，
> 所以 `more_eq` 能正确命中"粗体及以上"。
> 用 CSS 的 600 是**错的**——那个刻度上没有一个字体落在 600。

**目标推荐规则**：目标必须有真粗体、必须覆盖中文；
类别相同优先（宋体 → 宋体类粗体，楷体 → 楷体类粗体）；
同类别没有合适的，退到该类别的默认目标（Noto Serif/Sans CJK SC）。

**撤销**：删掉 `~/.config/fontconfig/conf.d/99-boldgen-aliases.conf` 即可完全还原。

---

## 常见问题

### 生成之后 WPS 里还是黑块？

1. 确认 fontconfig 已经看到新字体：
   ```bash
   fc-match "宋体:bold"
   ```
   应该指向 `~/.local/share/fonts/boldgen/` 下的产物。
2. 如果指向的还是原字体，可能是**旧的合成粗体文件排在前面**。
   检查 `~/.local/share/fonts/` 下有没有别的目录也放了粗体
   （本工具不扫描那个目录，会造成重复）。
3. **完全退出 WPS 再打开**——WPS 会缓存字体列表。

### 生成之后字体没有生效？

`fc-cache` 没跑成功。手动跑一次：

```bash
fc-cache -f
```

### 某个家族生成了，但效果不如预期？

试试调 `--strength`。另外注意有些字体（如 DFKai-SB、Simsun Founder Extended）
字形本身就是特殊设计，合成粗体未必好看。

### 怎么确认产物是好的？

```bash
boldgen check                     # 结构层面
boldgen mktest --out /tmp/t.docx  # 渲染层面
```
