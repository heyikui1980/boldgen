# 发布到 PyPI

这份文档写给**维护者**（也就是这个仓库的作者本人）。普通用户只需要看
[安装](../README.md#安装)那一节。

发布走 **trusted publishing**（PyPI 侧的 OIDC，不需要 API token）。
关键是先在 PyPI 上登记一个 **pending publisher**，第一次上传时 PyPI 会顺手把
`boldgen` 这个项目建出来，并把 pending publisher 转成正式的 publisher。

> **项目名 `boldgen` 在 PyPI 上目前是空的**（<https://pypi.org/pypi/boldgen/json>
> 返回 404），但 pending publisher **不占名字**——在真正发布之前，别人抢注
> 同一个名字，你的 pending publisher 就失效了。所以别提前几个月登记，
> 要发的时候再登记。

---

## 一、PyPI 侧的一次性配置

### 1. 登记 pending publisher

登录 <https://pypi.org> 后打开
<https://pypi.org/manage/account/publishing/>，点 **Add a new pending publisher**。

按 GitHub Actions 填：

| 字段 | 值 |
|---|---|
| PyPI project name | `boldgen` |
| Owner | `heyikui1980` |
| Repository name | `boldgen` |
| Workflow name | `publish.yml` |
| Environment name | `pypi`（可选，但建议填，和 workflow 里的一致） |

几个容易填错的点：

* **Workflow name 只填文件名** `publish.yml`，**不要**带 `.github/workflows/` 前缀；
* **Owner 大小写敏感**，填 `heyikui1980`；
* **Environment name 填了之后必须和 workflow 里的 `environment:` 对得上**。
  本仓库 `publish.yml` 里写的就是 `pypi`，所以填 `pypi`；
  填错的话 OIDC token 里的 `environment` claim 对不上，PyPI 会拒绝。

> **关于 GitHub 上的 `pypi` environment**
> 不需要手动建。GitHub Actions 第一次跑 `publish.yml` 时会自动建一个同名、
> 无任何保护规则的 environment（这个仓库已经建好了：
> <https://github.com/heyikui1980/boldgen/settings/environments>）。
> PyPI 的 trusted publisher 只认「项目名 + 仓库 + workflow 文件名」，
> environment 是可选的——填它只是为了多一份部署记录和一条指向 PyPI 项目页的链接。

### 2. 第一次发布

登记完 pending publisher 之后，**不需要**手动上传，也不需要任何 API token。
直接触发 workflow 即可：

```bash
cd ~/src/boldgen
# 想手动触发：
gh workflow run publish.yml -f confirm=yes
```

或者推一个新标签（`v*` 标签会触发）：

```bash
git tag v0.1.0 && git push origin v0.1.0
```

第一次成功上传时会发生三件事：

1. PyPI 上**自动创建** `boldgen` 这个项目；
2. pending publisher **自动转成**正式 publisher；
3. <https://pypi.org/project/boldgen/> 可以访问了。

之后发新版就只需要打标签。

### 3. 万一项目名被抢了 / 想先占名字

如果 pending publisher 因为项目名被别人抢注而失效（PyPI 会报
`invalid-publisher` 或 `400 Non-user identities cannot create new projects`），
或者你**想在第一次发布之前就锁定 `boldgen` 这个名字**，那就退回老路：
用一次性的 API token 手动上传。

在 PyPI 上创建 token：<https://pypi.org/manage/account/api-tokens/> →
**Create token** → 范围选 `pypi.org project` → 填 `boldgen`（项目还不存在时，
下拉框里选 `Entire account` 也行，但项目名范围更安全）→ 保存，
**token 只显示一次**。

```bash
cd ~/src/boldgen
.venv/bin/python -m build          # 生成 dist/*.whl 和 dist/*.tar.gz

# 上传（token 从环境变量读，别写进 shell 历史）
TWINE_USERNAME=__token__ \
TWINE_PASSWORD=pypi-xxxxxxxxxxxxxxxxxxxx \
.venv/bin/python -m twine upload dist/*
```

`twine` 在 `dev` extra 里：

```bash
.venv/bin/pip install ".[dev]"
# 或者不装到 venv，用 pipx 临时跑：
pipx run --spec twine twine upload dist/*
```

手动上传成功后，项目名就被锁住了，再去
<https://pypi.org/manage/account/publishing/> 把 pending publisher
配好（或者直接改成 API token 的 secret 方式），后续走自动发布。

### 4. 检查 PyPI 的渲染

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
.venv/bin/python -m twine check dist/*
```

`twine check` 会报 `PASSED` 才说明 metadata 和 markdown 都没问题。

---

## 二、之后的自动发布

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
「Publish to PyPI」这个 workflow。

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

## 四、排查

### `invalid-publisher: valid token, but no corresponding publisher`

OIDC token 是好的（说明 GitHub 侧的 workflow 没问题），是 **PyPI 侧找不到
匹配的 publisher**。逐项核对：

| PyPI 上的值 | 期望 |
|---|---|
| Owner | `heyikui1980`（大小写敏感） |
| Repository name | `boldgen` |
| Workflow name | `publish.yml`（只填文件名） |
| Environment name | `pypi`（如果填了的话） |

排查时 workflow 的日志会打印 OIDC token 的**全部 claims**（`sub`、`repository`、
`workflow_ref`、`environment` 等），拿它跟上面的表逐条对：

```bash
gh run view <run-id> --log-failed
```

### `400 Non-user identities cannot create new projects`

pending publisher 里填的项目名和包元数据里的名字对不上。
本项目的名字在 `pyproject.toml` 的 `name = "boldgen"`。

### `File already exists` / 版本已存在

PyPI 不允许覆盖同名版本。改了同样的内容想重发，只能**升版本号**。

---

## 五、别忘了这些

* **不要提交字体文件。** CI 会拦，但本地 `git add` 时留意 `git status`；
  `.gitignore` 已经挡了 `*.ttf` / `*.ttc` / `*.otf` / `*.otc`。
* **发版前跑测试**：`pytest -q` 必须全绿。
* **CHANGELOG 要写**。`docs/releases/vX.Y.Z.md` 可以直接当 GitHub Release
  的正文。
* **README 里的安装段要跟实际状态对齐**。PyPI 没发布之前要写
  「尚未发布」+ 源码安装方式，别写 `pipx install boldgen` 让用户白跑一趟。
