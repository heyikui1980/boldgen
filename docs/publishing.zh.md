# 发布到 PyPI

这份文档写给**维护者**（也就是这个仓库的作者本人）。普通用户只需要看
[安装](../README.md#安装)那一节。

发布分两步：

1. **第一次**必须手动上传（用 PyPI API token），因为 trusted publishing
   要求项目**已经存在**；
2. 之后每次发版都可以打标签让 CI 自动发布（trusted publishing，不需要 token）。

---

## 一、PyPI 侧的一次性配置

### 1. 账号与项目

* 注册/登录 <https://pypi.org>（用户名就是 `heyikui1980`）；
* 在 <https://pypi.org/manage/account/publishing/> 创建一个 **Pending publisher**：

  | 字段 | 值 |
  |---|---|
  | PyPI project name | `boldgen` |
  | Owner | `heyikui1980` |
  | Repository name | `boldgen` |
  | Workflow name | `publish.yml` |

  Pending publisher 是 PyPI 给你「一个还没发布过的项目」的占位符——**不需要 API token**，
  也不需要项目先存在。等第一次上传真的发生，PyPI 会自动把 pending publisher
  转成正式 publisher。

> **注意**：PyPI 的 trusted publisher 只认「项目名 + 仓库 + workflow 文件名」，
> **不关心 GitHub environment**。所以 `publish.yml` 里写的 `environment: pypi`
> 不是 trusted publishing 的必要条件，它只是用来挂一条部署记录 + 一个
> 指向 PyPI 项目页的链接。这个 environment 可以在
  <https://github.com/heyikui1980/boldgen/settings/environments> 手动建，
> **也可以不建**——GitHub Actions 第一次跑这个 job 时会自动建一个不带任何
> 保护规则的同名 environment。

### 2. 一次性的手动上传

第一次上传必须带 token，因为那时候 `boldgen` 这个项目在 PyPI 上还不存在
（`twine upload` 会顺手把项目建出来）。

**在 PyPI 上创建 token**：<https://pypi.org/manage/account/api-tokens/> →
`Create token` → 选 `pypi.org project` 范围 → 填 `boldgen`（项目还不存在时，
下拉框里选 `Entire account` 也行，但项目名范围更安全）→ 保存，
**token 只显示一次**。

然后在本机：

```bash
cd ~/src/boldgen
.venv/bin/python -m build          # 生成 dist/*.whl 和 dist/*.tar.gz

# 上传（token 从环境变量读，别写进 shell 历史）
TWINE_USERNAME=__token__ \
TWINE_PASSWORD=pypi-xxxxxxxxxxxxxxxxxxxx \
.venv/bin/python -m twine upload dist/*
```

没有装 twine 的话（`twine` 在 `dev` extra 里，装成 `.venv` 里应该有）：

```bash
.venv/bin/pip install ".[dev]"
# 或者不装到 venv，用 pipx 临时跑：
pipx run --spec twine twine upload dist/*
```

上传成功后：

* <https://pypi.org/project/boldgen/> 就能访问了；
* 那个 Pending publisher 会自动生效；
* **之后就不需要 token 了**，走下面的自动发布。

### 3. 检查 PyPI 的渲染

PyPI 项目页的正文来自 wheel 里的 `long_description`（也就是 `README.md`）。
PyPI 从 `pypi.org` 自己的域名渲染它，**README 里的相对链接会 404**。

本仓库的做法是：README 里所有指向仓库内文件的链接都写成绝对地址

```markdown
[`docs/cli.zh.md`](https://github.com/heyikui1980/boldgen/blob/main/docs/cli.zh.md)
```

而不是

```markdown
[`docs/cli.zh.md`](docs/cli.zh.md)
```

页内锚点（`#安装`）保持相对形式，那是页内跳转，不受影响。

改完 README 记得**重新 build**，否则 `dist/` 里还是旧的正文：

```bash
rm -rf dist && .venv/bin/python -m build
```

上传前可以本地预览一下 PyPI 会怎么渲染：

```bash
.venv/bin/pip install twine
.venv/bin/python -m twine check dist/*
```

`twine check` 会报 `PASSED` 才说明 metadata 和 markdown 都没问题。

---

## 二、之后的自动发布（trusted publishing）

CI 里已经有 `.github/workflows/publish.yml`，它做四件事：

1. 构建 sdist + wheel；
2. **检查发行包里没有字体文件**（`.ttf` / `.ttc` / `.otf` / `.otc`）——
   这是授权边界的技术兜底，衍生字体绝不能进发行包；
3. 换成 OIDC token；
4. 调 `pypa/gh-action-pypi-publish` 上传。

发新版：

```bash
cd ~/src/boldgen
# 先改 CHANGELOG.md，版本号在 pyproject.toml 里
.venv/bin/python -m pytest -q
.venv/bin/python -m build
git commit -am "chore(release): 0.2.0"
git push origin main
git tag v0.2.0 && git push origin v0.2.0   # ← 这一推会触发发布
```

推完标签后去 <https://github.com/heyikui1980/boldgen/actions> 看
「Publish to PyPI」这个 workflow。也可以手动触发（workflow_dispatch 输入
`confirm=yes`）。

> **tag 要打在 `main` 上**，且标签推送的 commit 必须已经推到了 GitHub，
> 否则 `actions/checkout` 拿不到代码。

---

## 三、GitHub Release 的产物

GitHub Release 上的 `boldgen-<版本>-py3-none-any.whl` 和
`boldgen-<版本>.tar.gz` 是从 `dist/` 直接搬过去的，方便不装 Python 的人下载。

```bash
gh release upload v0.2.0 dist/* --clobber
```

注意：GH Release 上的资产和 PyPI 上的包是**两次独立上传**，
改了 README 之后要**两个地方都更新**，否则会出现
「GH 上的是旧正文、PyPI 上的是新正文」的不一致。

---

## 四、别忘了这些

* **不要提交字体文件。** CI 会拦，但本地 `git add` 时留意 `git status`；
  `.gitignore` 已经挡了 `*.ttf` / `*.ttc` / `*.otf` / `*.otc`。
* **发版前跑测试**：`pytest -q` 必须全绿。
* **CHANGELOG 要写**。`docs/releases/vX.Y.Z.md` 可以直接当 GitHub Release
  的正文。
* **README 里的安装段要跟实际状态对齐**。PyPI 没发布之前要写
  「尚未发布」+ 源码安装方式，别写 `pipx install boldgen` 让用户白跑一趟。
