# 游戏发售笔记

在线网站：https://game-notes-upcoming.pages.dev/

源码仓库：https://github.com/Clay10096/game-notes-upcoming

独立的 Nintendo Switch 2 / PlayStation 5 即将发售游戏网站。首页只展示港、日、美三个商店区服的待发售游戏，不连接折扣站、App、游戏库或愿望单。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `site/` | **直接发布的静态目录**，根目录是 `index.html`；没有构建命令 |
| `site/data/upcoming-{ns2,ps5}-{hk,jp,us}.json` | 六份独立的有效游戏快照 |
| `site/data/*.status.json` | 各来源最近一次采集状态；失败时不改动有效快照 |
| `site/data/fx.json` | 欧洲央行参考汇率换算的人民币估价 |
| `scripts/scrape_upcoming.py` | 分别读取 Nintendo 与 PlayStation 官方公开页面／接口 |
| `scripts/exchange.py` | 更新参考汇率 |
| `scripts/check_site.py` | 发布前检查首页、资源和六份有效快照 |
| `.github/workflows/` | 推送发布及三地当地 00:05 的定时采集 |
| `tests/` | 日期精度、版本、优惠、旧数据保留与筛选测试 |

网站按需读取所选商店和区服的 JSON。页面展示官方名称、版本、封面、发售日、当地价格、人民币参考价及官方商品链接；公开预购优惠与 PS Plus 会员优惠分开显示。官方只公布年份、季节或“待定”时保留原文，不推算日期或价格。标准版优先，其他完整游戏版本放在版本选择中。已到准确发售日的条目会从页面和下一次快照中移除；只有大致日期的条目等官方更新。

## 本地检查

需要 Python 3.12、Node.js 22 或更新版本。

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
npm test
python3 scripts/check_site.py
python3 -m http.server 8767 --directory site
```

随后打开 `http://127.0.0.1:8767/`。直接双击 `index.html` 的 `file://` 页面无法通过浏览器读取本地 JSON。

手动更新示例：

```bash
python3 scripts/scrape_upcoming.py --store nintendo --region hk
python3 scripts/scrape_upcoming.py --store playstation --region hk
python3 scripts/exchange.py
```

采集、数据字段与限制见 [数据说明](docs/DATA.md)。独立 GitHub 仓库和 Cloudflare Pages 的配置见 [部署说明](docs/DEPLOYMENT.md)。
