# 数据来源与显示规则

每份快照都有 `kind: "upcoming"`、`store`、`region`、`timezone`、`currency`、实际采集完成的 `updatedAt`、`status`、`gameCount`、`source`、`games`。条目保留官方的 `releaseDateRaw`、`datePrecision`、可选商品 `id`、售价、普通优惠与会员优惠及优惠截止时间。没有精确日期或价格的字段为 `null`，页面按“待定”或“未公布”显示。

六个独立来源：

| 商店 | 港服 | 日服 | 美服 |
| --- | --- | --- | --- |
| Switch 2 | [Nintendo HK 目录](https://www.nintendo.com/hk/games/switch2/lineup)及公开分页、价格接口 | [Nintendo JP 目录](https://www.nintendo.com/jp/games/switch2/index.html)及公开搜索数据 | [Nintendo US Coming Soon](https://www.nintendo.com/us/store/games/coming-soon/)公开页面数据 |
| PS5 | [PlayStation HK 待发售分类](https://store.playstation.com/zh-hant-hk/category/3bf499d7-7acf-4931-97dd-2667494ee2c9/1) | [PlayStation JP 待发售分类](https://store.playstation.com/ja-jp/category/0c9f6f09-d84c-433e-9acd-d7e222eef034/1) | [PlayStation US 待发售分类](https://store.playstation.com/en-us/category/82ced94c-ed3f-4d81-9b50-4d4cf1da170b/1) |

PS5 使用各区商店当前公开的分类数据，再读取商品详情中的发售日、售价和公开优惠。Nintendo 美服来源是公开的 Coming Soon 精选页，可能没有收录所有待发售游戏。分类标识及页面结构是商店实现细节，可能变化；采集校验失败时**不覆盖上一份有效 JSON**，只更新对应 `.status.json`，网站提示该区数据已过期。静态快照不代表实时库存或最终售价。

仅收录完整的 NS2／PS5 游戏或游戏合集，排除试玩版、升级包及单独 DLC。版本归并依据官方商品关联信息与名称；名称差异过大时可能分成两条，避免误把不同游戏合并。页面对有明确日历日期的游戏执行发售日过滤；只有年份、季节或“待定”的游戏等待商店进一步更新。

`fx.json` 取[欧洲央行公布的参考汇率](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)，由 EUR 报价换算 USD／JPY／HKD 对 CNY，仅作参考。汇率失败也保留旧有效值，并单独显示其时间。汇率不是实际支付汇率。
