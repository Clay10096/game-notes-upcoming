# 独立部署到 Cloudflare Pages

本项目的发布目录固定为 `site/`，根目录有 `index.html`，**无需构建命令**。请为此项目使用独立的 GitHub 仓库和独立的 Cloudflare Pages 项目，例如 `game-notes-upcoming`；不要沿用或覆盖 `game-notes-eshop-deals`。

1. 在现有 Cloudflare 账号的 **Workers & Pages → Create application → Pages → Direct Upload** 建立新项目。生产分支设为 `main`，上传 `site/` 的**内容**，确认项目有自己的 `*.pages.dev` 地址。
2. 在 GitHub 新建独立仓库，默认分支 `main`，将本目录源码及 `.github/workflows/` 推送到仓库。静态快照是发布物的一部分，也需要入库；不要提交任何 API Token。
3. 仓库 **Settings → Secrets and variables → Actions → Variables** 新增 `HOSTING_PROVIDER=cloudflare` 和 `CLOUDFLARE_PAGES_PROJECT=<该新 Pages 项目实际名称>`。
4. 在同一处 **Secrets** 新增 `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`。Token 权限为 **Account → Cloudflare Pages → Edit**，资源只选择该项目所在账号。可复用权限和有效期适合的已有 Token；否则新建。Token 只填写在 GitHub Secret 中，不放入源码、终端日志或聊天。
5. 推送到 `main` 后，`pages.yml` 会测试源码及六份快照，然后通过 `cloudflare/wrangler-action` 将 `site/` 发布到这个 Pages 项目的 `main` 生产分支。检查 Actions 日志、Pages 部署记录、首页和 `/data/upcoming-ns2-hk.json` 等公开资源。
6. `hk.yml`、`jp.yml`、`us.yml` 各在 **Asia/Hong_Kong／Asia/Tokyo／America/Los_Angeles 当地 00:05** 运行；美国夏令时由 GitHub 的 IANA 时区调度处理。任务实际启动可能延迟，网站以 `updatedAt` 实际采集完成时间为准。每次刷新该区 NS2、PS5 和独立汇率快照，失败只更新状态，不清空旧快照；随后发布。Actions 的 `GITHUB_TOKEN` 需要仓库允许 **Read and write permissions**，以便把有效快照与状态提交回 `main`。

Cloudflare Pages Direct Upload 与 GitHub 仓库保持独立；此处的自动部署由 GitHub Actions 明确执行，不需要 Cloudflare 的 Git 集成。上线后修改一处可见的首页文字并再次推送，确认 Pages 生产部署更新。

## 本项目实际配置

- Pages 项目：`game-notes-upcoming`；生产分支：`main`。
- 公开网址：https://game-notes-upcoming.pages.dev/
- GitHub 仓库：https://github.com/Clay10096/game-notes-upcoming
- 发布目录：`site/`；无构建命令。
- 已配置上述两项 Variables 与两项 Secrets，并允许 Actions 提交快照。
- Cloudflare 发布令牌限定当前账号的 Pages 编辑权限，有效期至 2027 年 9 月 30 日；到期前需在 Cloudflare 创建替代令牌，并更新仓库的 `CLOUDFLARE_API_TOKEN` Secret。
