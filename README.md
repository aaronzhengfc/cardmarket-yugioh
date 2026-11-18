# Cardmarket 游戏王价格归档

GitHub Actions 每天 04:17 UTC（香港时间 12:17）下载 Cardmarket 官方 `price_guide_3.json`，验证生成日期、商品 ID 和价格后，将原始 JSON 无损压缩并保存在同一仓库的 `cardmarket-price-archive` 分支，按官方快照日期命名。这个分支不参与 App 构建。

每份 `.json.gz` 旁有 `.json.meta.json`，记录官方生成时间、数据源、原始文件 SHA-256 和商品数。相同文件不会重复提交；同一天文件内容不同、当日数据尚未发布或下载失败时，任务会失败而不会覆盖已有数据。可在 GitHub Actions 手动运行 `Archive Cardmarket Yu-Gi-Oh prices` 重试。GitHub 定时任务可能延迟，仓库长期不活跃时可能自动暂停；缺失日期不能由当前文件还原。

要将下载的快照加入本机 SQLite 归档，可以先解压后执行：

```sh
python3 scripts/cardmarket_history.py --file /path/to/price-guide.json
python3 scripts/cardmarket_history.py --status
```

本地 SQLite 和 GitHub 归档互相独立。旧数据不会自动上传；GitHub 分支仅从流程首次成功运行后开始积累。私有仓库保留访问限制；如果仓库公开，历史分支的文件也会公开。未来若在 App 或服务器展示数据，应确认 Cardmarket 的适用条款。

## 生成每张卡最近 90 天的价格文件

GitHub Actions 继续每天保存官方的原始快照。要生成上传 OSS 的文件，在本地运行：

```sh
cd /Users/fuchengzheng/Documents/github/cardmarket-yugioh
git fetch origin +refs/heads/cardmarket-price-archive:refs/remotes/origin/cardmarket-price-archive
python3 scripts/export_card_history.py \
  --mapping-db ../yugioh/docs/local-data/cards-maintenance.cdb \
  --output "exports/history-$(date +%Y-%m-%d-%H%M%S)"
```

脚本读取归档中最新快照日期及之前 89 个自然日内的快照，将每个快照对应的商品价格汇总为每张卡的当日最低、最高、平均价格和参与商品数。只保存实际存在的日期，不插值或补造。`manifest.json` 列出原始快照日期、校验值及使用的映射数据库校验值。没有对应价格时不会生成当天的记录。每次输出到一个新的目录，不会覆盖以前的导出。

把输出目录里的 `cards` 和 `manifest.json` 上传到 OSS 的同一根目录，保留路径。例如某张卡的文件为 `https://你的域名/price/cards/89631139.json`。每天生成的文件上传时覆盖 OSS 上对应的旧文件，而不是按日期建立目录；`manifest.json` 最后上传。上传期间不同卡文件可能暂时处于不同版本。不同日期使用相同的本地 `cards-maintenance.cdb` 映射重新计算；映射发生改变时，历史统计也可能改变。映射不再包含的卡牌需要从 OSS 清理旧文件。

每张卡文件采用 schemaVersion 4。`products` 为各 Cardmarket 商品的价格明细，每个商品保存 `idProduct`、`idMetacard`、`idExpansion`、`name` 和 `history`；后者每一天的 `prices` 保留原价目表的所有字段，包括 null 和 0。不同商品版本不合并。`idExpansion` 是 Cardmarket 系列 ID；目前没有可靠的系列名、卡号和稀有度映射，不能仅凭这些字段准确匹配 App 的印刷版本，需另行取得可信的对应资料。商品元数据来自当前维护库，不是按历史日期归档的元数据，映射会随维护库更新而变。

每张卡文件的 `history` 里每一天都包含 `date`、`minimum`、`maximum`、`average` 和 `productCount`。统计方法与 App 原有汇总一致：先从该卡对应商品筛出大于零的 `low`，然后取最小值、最大值及按商品等权计算的平均值。不是官方 `avg7` 或 `avg30` 字段，也不是成交价。`updatedAt` 是最新来源快照时间。App 原有参考价格面板仍使用内置快照，日期可能不同。

配置 `CARDMARKET_HISTORY_BASE_URL = https:/$()/你的域名/price/` 到 App 的 `Config/Local.xcconfig` 并重新构建。App 查看一张卡时下载该卡唯一的 JSON，7、30、90 天选项从文件筛选，不再请求其他日文件。缺失日期不会连线。无需 OSS 密钥；按需设置 CDN 缓存时间。

包括商品明细后，文件比仅保存汇总大得多。App 目前只展示卡牌汇总走势图，暂不支持按印刷版本选择；明细可供后续开发解析使用。

旧的 `2026-11-17-card-history`、`2026-11-17-initial`、`2026-11-17-all-prices` 及 `exports/daily` 是旧格式，不适用于本流程。`exports/` 不纳入 Git；数据由你手动上传。按天归档是 GitHub 原始数据；OSS 使用按卡文件。
