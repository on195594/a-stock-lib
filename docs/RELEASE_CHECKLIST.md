# 发版清单

适用于 `a-stock-lib` 版本变更。当前直接消费者是 `a-stock-agent-skills` runtime 和 `a-share-research` 应用。Skills 中的 research/monitor/QA 不单独安装本包；独立应用 `a-share-research` 有自己的依赖与运行环境。Tracker 已停止，不列入消费者。

消费者职责见[项目契约](https://github.com/on195594/a-share-research/blob/main/docs/project-contract.md)。本文只维护实际发版验证，不要求日常文档修改安装或升级消费者。

## 步骤

1. 在本仓运行全量测试和静态检查，确认版本同时更新于 `pyproject.toml`、`a_stock_lib/__init__.py` 与 `CHANGELOG.md`。
2. 运行 `python3 -m build`，确认 wheel metadata、源码版本和文件清单一致。
3. 发版前核对消费者的依赖元数据、锁文件及真实导入；仅验证实际使用本包的运行环境，不按旧仓库清单强制安装。
4. 在隔离验证环境核对两个消费者对候选 wheel 的真实调用，不切换活动客户端或生产环境。消费方验证见下表；公共 API、错误或时效语义变化时，两方都纳入影响判断。实际升级按各自授权进行，未验证项必须明确记录。
5. 从源码树外的随机 cwd 核对各实际消费环境的 `importlib.metadata.version("a-stock-lib")` 和 `a_stock_lib.__file__`，防止误用源码工作目录掩盖安装漂移。
6. 只更新发生变化的公共 API 文档、CHANGELOG 和实际发版消费方的锁文件/部署记录；不在 AGENTS/CLAUDE/README 多处复制版本和生产状态。历史 CHANGELOG/spec 不改写时点事实。
7. 复查本仓与实际发生变更的消费仓 diff。生产配置、cron、数据库或部署状态仍需独立授权。

## 消费方验证

| 消费者 | 安装身份与适用检查 |
|---|---|
| `a-stock-agent-skills` | 在隔离安装根与状态目录，用显式 `--a-stock-lib-source` 或 `--a-stock-lib-wheel` 运行 installer；确认 `a-stock-lib-install.json` 的版本、source commit 与 wheel hash，按本仓 development 约束运行全量测试。不能把候选安装到活动客户端。 |
| `a-share-research` | 在隔离项目环境中安装候选 wheel 并确认实际导入；用该环境的 `python -m pytest -q tests` 运行测试。受影响的财务/估值 Provider 用真实数据核对字段、单位、期间、来源与时效；影响研究输入语义时按其方案跑 11 家评估集并抽读报告。Lib 自身测试仍保持无真实网络。 |

候选验证期间使用对应隔离环境的解释器/检查工具，或 `uv run --no-sync`；不能让自动同步将候选 wheel 换回旧锁定版本。安装后、测试后均在源码树外核对实际包身份。消费仓正式更新依赖与锁文件后，再以其正常同步流程验证锁定安装。

未升级的消费者保留原锁定版本，不将候选测试宣称为已部署。研究应用的真实取数和模型验证遵守其既有授权与评估规则。

## 验收锚点

- 各实际消费者导入获批版本，且 wheel hash/source commit 可追溯。
- 使用 TuShare 的消费环境与本包声明的 SDK 版本兼容。
- wheel/sdist 不携带 Agent prompt、rubric、installer 或客户端发布逻辑。
- 本仓与实际升级的消费者全量测试通过。
