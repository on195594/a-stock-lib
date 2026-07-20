# 发版清单

用途：把之前每次发版本时靠记忆/翻 CHANGELOG 重建的步骤固化下来，减少下游（tracker/research）
版本漂移风险。适用范围：`a_stock_lib` 任何版本号变更（patch/minor 均适用）。

## 消费方现状（写清单前已核实，非假设）

| 消费方 | 形态 | 安装位置 | 版本锁定方式 |
|---|---|---|---|
| `a-stock-tracker` | 独立 git 仓库，有自己的 `.venv` | `~/a-stock-tracker/.venv/lib/python3.13/site-packages` | `requirements.txt` 内 `--find-links ../a-stock-lib/dist` + `a-stock-lib==X.Y.Z` 固定行 |
| `a-stock-research` | Claude Skill 目录（无独立 git 仓库），跑在系统/用户 Python 下 | `~/.local/lib/python3.13/site-packages`（`pip install --user`） | `requirements.txt` 里用注释记录版本号和安装命令（因为本地路径 wheel 不能写成可被 `pip install -r` 直接解析的依赖行） |
| `a-stock-monitor` | 无独立代码，通过 research 的 `cache.py`/skill 流程间接消费 | 不适用 | 不适用，随 research 同步 |

## 步骤

1. **发版前置检查**
   - `git status` 确认工作区干净
   - `pytest tests/ -v`，全量必须通过，记下通过条数（后面要写进文档）

2. **版本号 + CHANGELOG**
   - `pyproject.toml` 的 `version`
   - `a_stock_lib/__init__.py` 的版本常量
   - `CHANGELOG.md` 新增一节，写清 Added/Changed/Fixed，以及本轮 collab-pipeline 执行复盘（若有 codex/agy 参与）

3. **构建**
   ```bash
   cd ~/a-stock-lib && source .venv/bin/activate
   python3 -m build
   ```
   产出 `dist/a_stock_lib-X.Y.Z-py3-none-any.whl` + `.tar.gz`，不要用 `pip install -e` 软链接给任何消费方。

4. **安装进 `a-stock-tracker`**
   - 更新 `~/a-stock-tracker/requirements.txt` 里的 `a-stock-lib==X.Y.Z` 固定行
   - `cd ~/a-stock-tracker && source .venv/bin/activate && pip install -r requirements.txt`
   - 改动 tracker 仓库文件前，注意本仓库 CLAUDE.md 红线：tracker 工作区若有未提交改动，改它的文件（包括 `requirements.txt`）前必须先向用户确认

5. **安装进 `a-stock-research`（skill 目录）**
   - `pip install --user ~/a-stock-lib/dist/a_stock_lib-X.Y.Z-py3-none-any.whl`
   - 更新 `~/.claude/skills/a-stock-research/requirements.txt` 里的注释版本号

6. **跑消费方测试，不只信任 codex/agy 的转述**
   - tracker：`cd ~/a-stock-tracker && source .venv/bin/activate && pytest -q`
   - research：`cd ~/.claude/skills/a-stock-research && bash tests/run_all.sh`（统一执行 pytest 严格 warning 门禁和 `tests/test_check_holdings_cron.sh`）
   - 把两边真实通过条数记下来，不要用上一次版本的旧数字

7. **同步文档（新版本号 + 最新全量测试条数）**
   - 本仓库：`CLAUDE.md` / `AGENTS.md` / `README.md` 的"当前状态"段落（`AGENTS.md` 如果是 `prompts/` 渲染出来的部分，跑 `python3 scripts/render_prompts.py` 而不要手工改，避免引号/格式漂移）
   - tracker：`docs/project-status.md`
   - research：`CLAUDE.md`（或对应状态文件）
   - 三份文档的版本号必须一致，不允许任何一方停留在旧版本口径（这是 P0 任务的验收标准）

8. **提交**
   - 本仓库改动：PM 在 `a-stock-lib` 内有 standing authorization，可直接 commit
   - tracker/research 改动：不在 `a-stock-lib` 的 standing authorization 范围内，commit 前必须先跟用户确认

## 一致性校验锚点

- 三个消费方文档里的版本号字符串必须能用同一个 `grep -rn "a-stock-lib==" ~/a-stock-tracker/requirements.txt ~/.claude/skills/a-stock-research/requirements.txt` 交叉核对
- `collab-retro` 的 `project.status_files`（`CLAUDE.md`/`AGENTS.md`/`README.md`）会自动检查本仓库这三份文件是否有"当前状态"段落过期，但**不检查 tracker/research 那两份**，这两份仍需人工在本清单第 7 步核对
