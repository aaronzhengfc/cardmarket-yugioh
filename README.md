# Cardmarket 游戏王价格归档

GitHub Actions 每天 04:17 UTC（香港时间 12:17）下载 Cardmarket 官方 `price_guide_3.json`，验证生成日期、商品 ID 和价格后，将原始 JSON 无损压缩并保存在同一仓库的 `cardmarket-price-archive` 分支，按官方快照日期命名。这个分支不参与 App 构建。

每份 `.json.gz` 旁有 `.json.meta.json`，记录官方生成时间、数据源、原始文件 SHA-256 和商品数。相同文件不会重复提交；同一天文件内容不同、当日数据尚未发布或下载失败时，任务会失败而不会覆盖已有数据。可在 GitHub Actions 手动运行 `Archive Cardmarket Yu-Gi-Oh prices` 重试。GitHub 定时任务可能延迟，仓库长期不活跃时可能自动暂停；缺失日期不能由当前文件还原。

要将下载的快照加入本机 SQLite 归档，可以先解压后执行：

```sh
python3 scripts/cardmarket_history.py --file /path/to/price-guide.json
python3 scripts/cardmarket_history.py --status
```

本地 SQLite 和 GitHub 归档互相独立。旧数据不会自动上传；GitHub 分支仅从流程首次成功运行后开始积累。私有仓库保留访问限制；如果仓库公开，历史分支的文件也会公开。未来若在 App 或服务器展示数据，应确认 Cardmarket 的适用条款。
