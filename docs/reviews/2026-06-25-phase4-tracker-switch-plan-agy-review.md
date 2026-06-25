# Phase 4 tracker 切换计划 agy 审查记录

日期：2026-06-25
审查对象：`docs/plans/2026-06-25-phase4-tracker-switch-plan.md`
结论：修订后无遗留 Blocker / High / Medium 问题，可以作为 Phase 4 执行计划使用。

## 初审发现

`agy` 初审发现 1 个阻塞、2 个高危和若干中低风险：

- Blocker：`lib/market_data.py` 包装层若通过 `TushareMarketDataProvider().token` 或 `read_tushare_token()` 做门禁，会被共享包默认 `.env` 兜底绕过，导致 `SOURCE_DISABLED` 测试隔离失效。
- High：BaoStock-only backfill 可能被 `.env` token 重新注入干扰，无法强制只走 BaoStock。
- High：遗漏 `scripts/probe_tushare_market_data.py`，删除旧 provider 文件后探针脚本会 `ImportError`。
- Medium：`requirements.txt` 示例写死 `/home/lin/...` 绝对路径，不适合跨环境部署。
- Medium：dry-run 顺序应先跑 probe 生成新报告，再跑 readiness，避免读取迁移前旧报告。
- Low：缺少显式 BaoStock-only dry-run；回滚方案需要降低高压场景下的人工作业风险。

## 已采纳修订

- 明确 tracker 包装层以 `os.environ["TUSHARE_TOKEN"]` 为唯一真理源；`.env` 只由 `pipeline.py` / probe 预先加载到环境变量。
- 明确 `TUSHARE_TOKEN="" MARKET_DATA_ALLOW_BAOSTOCK_ONLY=1` 用于强制 BaoStock-only backfill。
- 将 `scripts/probe_tushare_market_data.py` 和 tracker `CLAUDE.md` 纳入允许修改范围。
- 将 requirements 示例改为 `--find-links ../a-stock-lib/dist` + `a-stock-lib==0.1.1`，并禁止写死 `/home/lin/...`。
- 调整 dry-run 顺序为 probe 先于 readiness。
- 增加 BaoStock-only dry-run 验收。
- 增加 Phase 4 前安全 tag；保留 revert 作为默认回滚方式，不把 `git reset --hard` 作为默认步骤。

## 复查结果

`agy` 复查确认以下问题均已关闭：

- Token/.env 门禁绕过 `SOURCE_DISABLED`
- BaoStock-only backfill 干扰
- 遗漏 `scripts/probe_tushare_market_data.py`
- requirements 绝对路径
- readiness/probe 顺序
- BaoStock-only dry-run 缺失

复查结论：没有遗留阻塞、高危或中危问题。
