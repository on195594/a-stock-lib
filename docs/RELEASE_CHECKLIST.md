# 发版清单

适用于 `a-stock-lib` 版本变更。当前直接消费者是 `a-stock-agent-skills` runtime；research/monitor/QA 不再单独安装本包。Tracker 已合并 screen 且不再依赖本包，不为本包发版重新添加该依赖。

## 步骤

1. 在本仓运行全量测试和静态检查，确认版本同时更新于 `pyproject.toml`、`a_stock_lib/__init__.py` 与 `CHANGELOG.md`。
2. 运行 `python3 -m build`，确认 wheel metadata、源码版本和文件清单一致。
3. 发版前核对消费者的依赖元数据、锁文件及真实导入；仅验证实际使用本包的运行环境，不按旧仓库清单强制安装。
4. agent-skills：以显式 `--a-stock-lib-source` 或 `--a-stock-lib-wheel` 运行 installer，确认生成的 `a-stock-lib-install.json` 记录版本、source commit 与 wheel hash，再运行全量测试。
5. 从源码树外的随机 cwd 核对各实际消费环境的 `importlib.metadata.version("a-stock-lib")` 和 `a_stock_lib.__file__`，防止误用源码工作目录掩盖安装漂移。
6. 只更新发生变化的公共 API 文档、CHANGELOG 和实际发版消费方的锁文件/部署记录；不在 AGENTS/CLAUDE/README 多处复制版本和生产状态。历史 CHANGELOG/spec 不改写时点事实。
7. 复查本仓与实际发生变更的消费仓 diff。生产配置、cron、数据库或部署状态仍需独立授权。

## 验收锚点

- 各实际消费者导入获批版本，且 wheel hash/source commit 可追溯。
- 使用 TuShare 的消费环境与本包声明的 SDK 版本兼容。
- wheel/sdist 不携带 Agent prompt、rubric、installer 或客户端发布逻辑。
- 本仓与实际升级的消费者全量测试通过。
