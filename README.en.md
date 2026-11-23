# boldgen — bake real Bold faces for families that have none

[![CI](https://github.com/heyikui1980/boldgen/actions/workflows/ci.yml/badge.svg)](https://github.com/heyikui1980/boldgen/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**WPS on Linux renders bold Chinese text as smeared black blobs.**
`boldgen` bakes a real Bold font file for every family that lacks one, so that
*every* application can match a genuine bold face instead of having to fake it.

```
$ boldgen scan --missing-bold
共 51 个字体家族（仅中文字体）：

家族                                          状态  中文  源文件
--------------------------------------------  ---  --  -------------------------------
AR PL UKai CN                                 缺粗体  是  /usr/share/fonts/truetype/arphic/ukai.ttc#0
LiSu (隶书)                                   缺粗体  是  /usr/share/fonts/truetype/winfonts/SIMLI.TTF
SimHei (黑体)                                 缺粗体  是  /usr/share/fonts/truetype/winfonts/simhei.ttf
...

$ boldgen generate --family SimSun --family SimHei
✓ 生成 2 个粗体 face：
    SimSun    SimSun-Bold.ttf  字形 28862  半径 4  10.1 MB
    SimHei    SimHei-Bold.ttf  字形 8192  半径 4  2.9 MB
  合计 13.0 MB
  已安装到 /home/you/.local/share/fonts/boldgen
  fontconfig 缓存已刷新
```

> **Note:** the CLI's own messages are currently Chinese-only; `--json` output uses
> English/ASCII field names, so it is the machine-readable surface for scripts.
> Pull requests that add an English UI are welcome.

---

## Table of contents

- [The problem](#the-problem)
- [It is not WPS's fault, and not the font's fault](#it-is-not-wpss-fault-and-not-the-fonts-fault)
- [What boldgen does](#what-boldgen-does)
- [Two approaches](#two-approaches)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Verifying the result](#verifying-the-result)
- [What it does not do](#what-it-does-not-do)
- [Known limitations](#known-limitations)
- [Licensing](#licensing)
- [Documentation](#documentation)
- [中文文档](README.md)

---

## The problem

Open a Chinese document in WPS Writer on Linux and turn on **bold**:

| Family | Regular | Bold |
|---|---|---|
| SimSun (宋体) | fine | **black blob** |
| SimHei (黑体) | fine | **black blob** |
| KaiTi (楷体) | fine | **black blob** |
| Noto Sans CJK SC | fine | fine (it ships a real bold) |

The rule is simple: **when a family has no real Bold face, bold turns into a blob.**

## It is not WPS's fault, and not the font's fault

Here is what the investigation turned up:

1. **The font files are fine.** The very same fonts render bold perfectly in
   Chrome (Skia + fontconfig `embolden`).
2. **fontconfig is not at fault.** Same machine, same fontconfig: Chrome is fine,
   WPS is not.
3. **`unitsPerEm` is not at fault.** Control fonts built with `upem=1000/1024`
   blob identically.
4. **WPS's own synthetic-bold implementation is buggy.**
   WPS Writer's renderer (`libkso.so`) calls `FT_Load_Glyph` / `FT_MulFix` but
   **not** FreeType's `FT_Outline_Embolden`; it implements its own outline
   dilation, which overshoots by several times.

Measured ink area of the bold text, relative to regular:

| | normal fake bold | boldgen's baked bold | WPS with the bug |
|---|---|---|---|
| ink ratio | 1.2 – 1.5 | **1.85** | **2.3 – 10.2** |

> The full evidence chain is in [`docs/how-it-works.zh.md`](docs/how-it-works.zh.md).

**So the fix is not "patch WPS" — it is "give these families a real bold".**
Once fontconfig can match a genuine Bold face, the application never has to
synthesize one, and WPS's bug is bypassed. Other applications benefit too.

## What boldgen does

For every family on the system that lacks a bold face:

1. Scan fontconfig, group fonts by family, and identify the families with no bold.
2. Pick the family's regular-weight face as the source.
3. **Dilate the outline** of every glyph (real geometric dilation, not a
   bold-filter) and write out a brand-new Bold font file with complete
   metadata (`name` / `OS/2` / `head`).
4. Install it into `~/.local/share/fonts/boldgen/` (user-level, no sudo) and
   refresh the fontconfig cache.

The **glyph shapes do not change** — only the strokes get thicker. It is the
same kind of operation FreeType and Skia perform when synthesizing bold, but
with a carefully verified geometric implementation.

### The geometry

Modelled on FreeType's `FT_Outline_Embolden`, with two fixes:

- **Miter failure falls back to a bevel** instead of clamping the miter
  length — clamping leaves a long spike of 4× the radius at concave corners,
  which is the most visible artifact of naive synthetic bold.
- **Implied on-curve midpoints are materialized** as explicit points, so the
  joins at corners are geometrically exact.

## Two approaches

`boldgen interactive` lets you pick between them with a single selection:

| | Generator | fontconfig alias |
|---|---|---|
| What it does | bakes a real Bold font file | redirects "family + bold" requests to another family that has a bold |
| Glyphs | **unchanged**, just thicker | **become the target's** |
| Disk | one more file per family (tens of MB for CJK) | none |
| Works in | any application | fontconfig-aware applications only |
| Undo | `boldgen uninstall` | delete one config file |

**The generator is the default.** The alias mode is useful when disk space is
tight or when you just need a quick stand-in.

## Installation

```bash
pipx install boldgen                          # from PyPI (once published)
pipx install "git+https://github.com/heyikui1980/boldgen"   # from source
```

Zero required dependencies — pure Python 3.9+ standard library.

> **CFF/OTF outlines** (`.otf`) are **not supported** yet — the built-in engine
> only handles TrueType (`glyf`) outlines. Such fonts raise a clear error
> rather than silently producing a broken file.

## Quick start

```bash
# 1. See which Chinese families lack a bold
boldgen scan
boldgen scan --missing-bold        # only the ones lacking bold
boldgen scan --json                # machine-readable

# 2. Interactive: pick families → choose an approach → confirm → run
boldgen interactive

# 3. Or name them directly
boldgen generate --family SimSun --family SimHei --family KaiTi

# 4. See what is installed
boldgen list
boldgen check          # reports stale products; also checks that bold requests really land on them

# 5. Undo
boldgen uninstall --family SimSun
boldgen uninstall --all
```

## Commands

| Command | What it does |
|---|---|
| `boldgen scan` | scan system fonts, list families and whether they have a bold |
| `boldgen interactive` | **main entry point**: scan → pick → choose approach → run |
| `boldgen generate` | generate bold faces for the given families |
| `boldgen alias` | fontconfig alias mode (list / write / remove rules) |
| `boldgen list` | list installed products |
| `boldgen check` | detect products made stale by a changed source font; verify bold requests actually match the products |
| `boldgen uninstall` | remove installed products |
| `boldgen mktest` | build a `.docx` for manual visual verification |

Full reference: [`docs/cli.zh.md`](docs/cli.zh.md).

## Verifying the result

**Rendering** is the only reliable acceptance criterion, so the tool ships with
a test-document generator:

```bash
boldgen mktest --out /tmp/t.docx --open
```

The document has two lines per font — one bold, one regular. Open it in WPS or
LibreOffice: the bold line should look like a proper bold, not a blob.

## What it does not do

- **Never** modifies, overwrites or deletes system font files. Products live
  only in `~/.local/share/fonts/boldgen/`; uninstalling means deleting that
  directory.
- **Never** touches `~/.config/fontconfig/fonts.conf`. The alias mode writes a
  single separate file, `~/.config/fontconfig/conf.d/99-boldgen-aliases.conf`;
  deleting it restores everything.
- **Never** downloads any font, and never uses the network.
- **Never** distributes any font file (see [Licensing](#licensing)).

## Known limitations

- **TrueType (`glyf`) outlines only.** CFF/OTF is not supported yet.
- **Composite glyphs are not dilated as a whole.** Their components are
  bolded individually and inherit the effect, but a scaled component's stroke
  weight scales with it.
- **Coordinates are quantized to integer font units.** A font with
  `unitsPerEm=256` (such as SimSun) has a minimum step of 1/256 em; the
  dilation radius is `round(256 × 0.015) = 4`.
- **Variable fonts are processed at their default instance only.**
- **Synthetic bold is never as good as a designed bold.** The baked face was
  not art-directed — but it is at least a *correctly rendered* bold.

## Licensing

The **software** is MIT licensed — see [`LICENSE`](LICENSE).

**Generated font files are not distributed with this project.** They inherit the
license of their source font:

| Font | May derived works be redistributed? |
|---|---|
| SimSun / SimHei / KaiTi / FangSong (Microsoft) | ✗ |
| Founder / ST / 华文 series | ✗ |
| Noto / Source Han / WenQuanYi / Arphic | per their own license |
| DejaVu / Liberation and friends | per their own license |

> See [`docs/licensing.zh.md`](docs/licensing.zh.md) and [`NOTICE`](NOTICE).

This project **distributes code only**. Generate derived fonts on your own
machine and respect the source font's terms.

## Documentation

| Document | Contents |
|---|---|
| [`docs/how-it-works.zh.md`](docs/how-it-works.zh.md) | the dilation algorithm + the full evidence chain for the WPS bug |
| [`docs/cli.zh.md`](docs/cli.zh.md) | complete reference for every subcommand |
| [`docs/licensing.zh.md`](docs/licensing.zh.md) | per-font license and redistribution table |
| [`docs/upstream/wps-issue.zh.md`](docs/upstream/wps-issue.zh.md) | issue template for WPS + minimal reproduction |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE) — but read [`NOTICE`](NOTICE) first.
