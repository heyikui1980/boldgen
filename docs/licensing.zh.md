# 授权与可再分发性

## 一句话结论

> **本项目只分发代码。**
> 生成的字体文件一律由用户在自己的机器上本地生成，
> 并**继承源字体的授权**。请勿把 SimSun / 方正 / 华文 等字体的衍生作品再分发。

---

## 为什么是这个边界

`boldgen` 做的事情是「基于某个字体文件，生成一个修改过的字体文件」。

修改过的字体文件在著作权法上属于**演绎作品**，其再分发权由源字体的授权决定，
而不是由生成工具的授权决定。生成工具是 MIT，但 MIT **只覆盖软件本身**。

所以：

* **代码**——MIT，随本项目分发，见 [`LICENSE`](../LICENSE)；
* **产物**——继承源字体授权，**不随本项目分发**。

这个边界也让本项目可以安全地帮助使用正版商业字体的用户：
你买了正版的宋体，生成一份自己机器上用的粗体是**你对自己软件的正常使用**；
但把这份衍生品打包上传，就是**再分发**。

---

## fsType：字体自己声明的嵌入权限

每个 TrueType 字体的 `OS/2` 表里有一个 `fsType` 字段（偏移 8，16 位），
声明字体作者允许的嵌入方式：

| 值 | 名称 | 含义 |
|---|---|---|
| `0x0000` | Installable Embedding | 可自由嵌入与再分发 |
| `0x0002` | Restricted License Embedding | 仅在授权条款允许时嵌入 |
| `0x0004` | Preview & Print | 仅供预览与打印 |
| `0x0008` | Editable Embedding | 可编辑嵌入（文档内可编辑） |
| `0x0100` | No Subsetting | 不允许子集化 |
| `0x0200` | Bitmap Embedding Only | 仅允许嵌入位图 |

**关键点：`fsType` 管的是「嵌入」，不是「再分发」。**
一个 `fsType = 0x0008` 的字体可以合法地嵌进你的 Word 文档，
但这不代表你可以把**修改过的它**上传到网上。

`boldgen` 生成的是**修改过的字体**（轮廓变了），所以适用的是「修改与再分发」条款，
这通常写在字体的 `name` 表 nameID 13（版权说明）里，或字体发行方自己的 EULA 里。

### 本机实测

```bash
# 查看某个字体的 fsType 与版权说明
python3 - <<'PY'
import struct
from fontTools.ttLib import TTFont        # 需要 fontTools；没有就用 boldgen 自己的解析器
f = TTFont("/usr/share/fonts/custom/simsun.ttc")
print(hex(f["OS/2"].fsType))
PY
```

用 `boldgen` 自带的零依赖解析器也可以：

```bash
python3 - <<'PY'
import struct, sys
sys.path.insert(0, "src")
from boldgen.sfnt import Font
f = Font(open("/usr/share/fonts/custom/simsun.ttc", "rb").read(), 0)
os2 = f.table_bytes("OS/2")
print("fsType =", hex(struct.unpack_from(">H", os2, 8)[0]))
print([r.text for r in f.names() if r.name_id == 13])
PY
```

---

## 各类字体的授权对照

下表是**本机实测**的 `fsType` 与 nameID 13 内容，以及各字体的公开授权。

### ✗ 不可再分发衍生作品

| 字体 | fsType | 授权 | 说明 |
|---|---|---|---|
| **SimSun**（宋体） | `0x0008` | Microsoft supplied font | 原文："Any other use is prohibited." |
| **SimHei**（黑体） | `0x0008` | Microsoft supplied font | 同上 |
| **KaiTi**（楷体） | `0x0008` | Microsoft supplied font | 同上 |
| **FangSong**（仿宋） | `0x0008` | Microsoft supplied font | 同上 |
| **DengXian**（等线） | `0x0008` | Microsoft supplied font | 同上 |
| **Microsoft YaHei**（微软雅黑） | `0x0008` | Microsoft supplied font | 同上 |
| **方正系列**（FZHei / FZKai / FZFangSong / FZXiaoBiaoSong） | `0x0008` | 方正字库 EULA | 需查阅方正官方授权条款 |
| **华文系列**（STSong / STKaiti / STFangsong / STXihei / STHupo / STLiti / STCaiyun / STXinwei） | `0x0008` | 中易 / 红旗字库授权 | 需查阅发行方授权条款 |

**这些字体的粗体你可以在自己机器上生成和使用，但不要把生成的文件发给别人。**

### ⚠️ 可以再分发，但有条件

| 字体 | fsType | 授权 | 条件 |
|---|---|---|---|
| **AR PL UMing / UKai** | `0x0000` | Arphic Public License | 必须保留 license 文件原文；必须**声明做了修改**；衍生作品必须同样自由可得 |
| **Noto Sans/Serif CJK** | `0x0000` | SIL OFL 1.1 | 见下方「OFL 的 Reserved Font Name」 |
| **Liberation** | `0x0000` | SIL OFL 1.1 | 见下方「OFL 的 Reserved Font Name」 |
| **DejaVu** | `0x0000` | Bitstream Vera + 公有领域改动 | 修改后**必须改名**，不能含 "Bitstream" 或 "Vera" |
| **WenQuanYi Zen Hei** | `0x0008` | GPL-2 + 字体嵌入例外 | 保留 GPL 声明 |
| **WenQuanYi Micro Hei** | `0x0008` | Apache License 2.0 | 保留许可声明与 NOTICE |
| **FreeSerif / FreeSans** | `0x0000` | GPL + 字体嵌入例外 | 保留 GPL 声明 |
| **Droid Sans Fallback** | `0x0000` | Apache License 2.0 | 保留许可声明 |
| **IPA Gothic** | `0x0000` | SIL OFL 1.1 | 见下方「OFL 的 Reserved Font Name」 |

### OFL 的 Reserved Font Name —— 一个容易踩的坑

SIL OFL 1.1 允许你自由修改和再分发字体，但有一个条件：

> 如果原字体声明了 **Reserved Font Name (RFN)**，
> 你**不能**用原来的名字发布修改后的版本。

Noto CJK 的 RFN 是 `Noto`，Liberation 的是 `Liberation`，
IPA Gothic 的 RFN 通常是 `IPA Gothic`。

**而 `boldgen` 恰恰保留了原家族名**——这是**故意**的：
只有家族名一致，fontconfig 才能把「宋体 + 加粗」匹配到这份产物，
否则整个工具就失去意义。

所以：

> **你可以用 `boldgen` 给 OFL 字体生成粗体并在本机使用；
> 但如果你打算把产物发给别人，必须先改名**（例如 `Noto Sans CJK SC Bold` → `Noto Sans CJK SC Bold Baked`）
> 并且**不能**使用原字体声明的 RFN。

本项目**不分发任何字体文件**，因此这个限制不影响本仓库的合规性；
它只影响你个人分发自己的产物时的做法。

### Arphic Public License 的「声明修改」要求

Arphic Public License 要求修改后的字体：

* 保留 `ARPHICPL.TXT` 原文；
* **在每个修改过的文件里插入显著的修改声明**（何时、如何修改）；
* 衍生作品同样自由可得。

`boldgen` 生成的每个文件都会在 `name` 表的 **nameID 5（版本字符串）** 里插入一条
显著的修改声明：

```
Version 1.000; Modified by boldgen 0.1.0: synthetic bold, glyph outlines
dilated by 15 font units (strength 0.015, unitsPerEm 1000)
```

声明里写明了**由谁改的、改了什么、改了多少**（工具版本、外扩半径、强度系数、
原始 upem），满足 Arphic "insert a prominent notice in each modified file
stating how and when you changed it" 的要求。TrueType 的 `name` 表没有专门的
"修改声明"字段，nameID 5 版本字符串是唯一既通用又会被字体查看工具显示的落点。

原字体的版权记录（nameID 0 / 13）原样保留。**不过**：如果你要再分发 Arphic 字体
的衍生作品，还需要在分发包里附上 `ARPHICPL.TXT` 原文，并保证衍生作品同样自由可得
——这两件事 `boldgen` 无法替你做，因为它们涉及分发行为本身。

---

## 实务建议

1. **默认**：生成给自己用。绝大多数场景（修 WPS 显示问题）都属于这一类。
2. **想分享产物**：先查源字体的授权，再决定是否改名、是否附上 license 文件。
3. **拿不准**：别分发。生成一份给自己用，成本为零。
4. **想给项目做贡献**：**只贡献代码和测试**，不要把生成的字体提交进仓库
   （`.gitignore` 已经挡住了 `*.ttf` / `*.ttc` / `*.otf`）。

---

## 本项目的授权声明

见 [`NOTICE`](../NOTICE)。要点：

* 本仓库不包含任何字体文件；
* 本仓库不下载、不打包、不分发任何字体；
* 生成的产物继承源字体授权；
* 保留家族名是工具功能所必需，但**不构成**对源字体授权的规避或授权。

---

## 相关链接

* [SIL Open Font License 1.1](https://openfontlicense.org/)
* [Bitstream Vera / DejaVu 授权](https://dejavu-fonts.github.io/License.html)
* [Arphic Public License](https://www.freedesktop.org/wiki/Software/CJKUnifonts)
* [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
* [Microsoft 核心字体 EULA](https://learn.microsoft.com/typography/fonts/font-faq)
* [WPS 字体版权说明](https://www.wps.cn/privacy/privacy_statement.html)
