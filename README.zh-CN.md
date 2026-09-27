# annals（中文说明）

> [!NOTE]
> **实验性项目。** 个人工具，欢迎反馈。v0.x 表示在一台机器上 `init` → `scan` → `backup` → `status` 可用——不是成品。
>
> [English README →](README.md)

**Agent CLI 把聊天记录当缓存；Annals 把它当成只增不减的 git 归档。**

Claude Code、Grok、OpenCode 会静默丢掉 transcript。Annals 按计划收获它们，CLI 删了也不删归档侧，并提交到本地 git 仓库。异地耐久靠你已有的系统备份；可选 git remote 用来跨机器。

当前适配器：**Claude Code**、**Grok**、**OpenCode**。仅 Unix。Python 3.12+，标准库，无运行时依赖。

完整约定见 [SPECIFICATION.md](SPECIFICATION.md)。

## 动机与场景

- CLI 会 prune / 丢掉会话；带 `--delete` 的同步工具会把归档一起毁掉。Annals **从不删除目标侧已有文件**。
- 适合「我只要这台机器上的对话别丢」——不是 GUI、不是公开 transcript、也不是点文件备份。
- 多机 = 每台一个分支/命名空间，**不会**自动合并，也没有跨机 resume。

## 快速开始

```bash
# 从 clone 安装
uv tool install .

annals init --machine mini
# 若本机没有 git 身份，init 会提示；backup 提交需要它。
# 可 `git config --global user.email you@example.com`
# 或在 ~/.config/annals/config.toml 取消注释 [git].author_email
annals scan
annals backup
annals status
```

定时：`recipes/launchd.plist`（macOS）或 `recipes/annals.timer`（systemd）。

## 已知限制

1. **适配器**仅 Claude Code / Grok / OpenCode——尚无 Cursor。
2. **正文不脱敏。** 请把归档当私有数据。
3. **尚无搜索索引**——以 git 为准（`git grep` / `git log`）。
4. **仅 Unix。** 多机 = 每机独立分支；无跨机 resume。
5. **优先从 clone 安装。** `git+` URL 安装取决于远端是否已就绪。

更完整的英文说明与设计取舍见 [README.md](README.md)。
