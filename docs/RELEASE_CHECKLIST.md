# 发版清单

适用于 `a-stock-lib` 版本变更。当前只有两个直接消费者：`a-stock-tracker` 与 `/home/lin/a-stock-agent-skills` runtime；research/monitor/QA 不再单独安装本包。

## 步骤

1. 在本仓运行全量测试和静态检查，确认版本同时更新于 `pyproject.toml`、`a_stock_lib/__init__.py` 与 `CHANGELOG.md`。
2. 运行 `python3 -m build`，确认 wheel metadata、源码版本和文件清单一致。
3. tracker：固定 `tushare==1.4.29` 与 `a-stock-lib==X.Y.Z`，安装新 wheel 后运行全量测试；不得恢复 BaoStock 依赖或 fallback。
4. agent-skills：以显式 `--a-stock-lib-source` 或 `--a-stock-lib-wheel` 运行 installer，确认生成的 `a-stock-lib-install.json` 记录版本、source commit 与 wheel hash，再运行全量测试。
5. 从随机 cwd 分别核对两个运行环境的 `importlib.metadata.version("a-stock-lib")` 和 `a_stock_lib.__file__`，防止误用源码工作目录掩盖安装漂移。
6. 同步本仓 `README.md`、`AGENTS.md`、`CLAUDE.md` 与两个下游的当前状态文档；历史 CHANGELOG/spec 不改写时点事实。
7. 复查三仓 diff。修改 tracker 或 agent-skills 的生产配置、cron、数据库或部署状态仍需独立授权。

## 验收锚点

- 两个下游实际导入同一版本，且 wheel hash/source commit 可追溯。
- tracker 与 agent-skills 的 TuShare 版本均为 `1.4.29`。
- wheel/sdist 不携带 Agent prompt、rubric、installer 或客户端发布逻辑。
- 本仓与两个下游全量测试通过。
