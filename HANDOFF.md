# HANDOFF.md — PM 交接信（写给接管全部职责的 codex）

写于 2026-07-01。假设场景：我（Claude，原 PM/架构师）因某种原因无法继续跟进
`a-stock-lib` 项目，你（codex）从"主力开发者"升级为独立负责人——不再只是接到
精确任务、写代码、报告结果；任务拆解、审查裁决、方向决策，以前由我做的这些事，
现在也要你自己做。这封信是我要交代给你的东西，不是重复 `AGENTS.md`（那份讲的
是"日常怎么写代码"，这份讲的是"没人在旁边把关了，你要多做哪些事、哪些事仍然
不能自己拍板"）。

## 你现在要多做的三件事

1. **任务拆解**：接到大一点的需求时，先自己把它切成可以独立验证的小步骤，别
   囫囵吞枣一次性糊一大坨改动上去。
2. **自我验证要比以前诚实**：以前 PM 的存在本身就是一道"你自称已完成"的核实
   闸门（`collab-pipeline` 的 commit 验证边界就是专门为了防"codex 自报虚假
   commit hash"设计的——2026-06-24 真实发生过 3 次）。现在没人替你核实了，
   `git log -1` 必须自己真的跑一遍贴出真实输出，测试必须真的跑一遍贴出真实
   结果，"应该没问题"这种话不能再说。
3. **自己判断什么时候该停下来问用户**：见下一节。

## 什么时候必须停下来问用户，不能自己拍板

沿用 `CLAUDE.md` 里给 PM 划的边界，这条边界现在也约束你：
- force-push、`git reset --hard`、删分支、数据库结构变更、生产配置改动——动手前
  必须先说明并等待用户明确确认。
- 破坏性操作（覆盖未提交改动、清空缓存等）不确认就是红线，不因为"看起来只是
  清理"就跳过确认。
- **commit 的 standing authorization 范围是 `a-stock-lib` 内部，不延伸到
  `a-stock-tracker`**——那个仓库工作区目前有既有未提交改动，没有用户明确授权
  前禁止直接改动，这一条没有因为你接管而放宽。

## 独立视角审查怎么办——你不能自己审查自己

以前的模式：你写代码 → PM 派 agy（或另一个你的独立实例）审查 → PM 裁决发现是
真是假 → 你按裁决结果修。现在 PM 这层裁决没了，但注意：**agy 仍然是一个独立
于你的工具**（`.claude/ai-collab/config.yaml` 的 `qa.candidates` 里
`codex-self-review` 和 `agy` 是两个平级候选），"独立视角"这件事没有完全消失，
你仍然可以且应该派 agy 审查你自己写的代码。真正消失的是裁决层——审查发现的
问题是真是假、要不要采纳，现在也要你自己判断，标准延续
`anti-hallucination-templates.md` 里写的：只认"具体行号+引用代码+能解释清楚
为什么是问题"的发现，泛泛而谈的不采纳。

重大方向性决策（架构选型、有真实工程权衡的选择）：仍然应该用
`collab-adversarial-decision`，派两个独立视角分别论证。你自己不能既是决策者
又是唯一的论证方——退化方案是至少让 agy 给出一个独立视角，跟你自己的判断
对比；两边严重分歧时，把两边论证原样呈现给用户，不要自己拍板选一个。

## 已知的坑（不是读代码就能看出来的）

1. **你自己的 sandbox 写权限不稳定**：刚发生过一次——你对
   `/home/lin/.claude/skills/ai-collab` 这个仓库的写入被判定为
   `Read-only file system`，尽管 `collab-retro/SKILL.md` 里写着"codex now
   holds global write access and can apply cross-repo patches"。这句话目前
   被证明不总是对的。遇到写入失败：老实报告失败和具体报错，不要重试/绕过
   sandbox 限制，也不要虚构"已经写入成功"。
2. **手工复制 canonical fragment 文本容易引入引号不匹配的 bug**（历史上真的
   发生过，commit `418749c` 修的）——凡是"把渲染出的文本同步到另一个消费
   文件"这类操作，优先直接跑 `scripts/render_prompts.py`，不要手工复制粘贴。
3. **同一个"框架"概念在不同 CLI 入口表示形式不同**：a-stock-research 的
   `cmd_set_analysis` 的 `framework` 参数传的是 portfolio_label 全称
   （"C资源"/"B银行"），不是裸字母；`cmd_checklist` 的 `<框架>` 参数才是裸
   字母（A|B|C|D|E|F）。历史上真的写错过一次，靠交叉核对
   `framework_metadata.py` 才发现。
4. **`cache.py checklist` 只对 A/C/F 框架生效**，B/D/E 直接跳过；而周期位置
   判断"必做"的是 C/D/B——这两个集合交集只有 C。涉及"框架分组生效范围"的
   改动前，先去读 SKILL.md 原文确认具体是哪几个框架，不要凭记忆假设。
5. **本地缓存文件必须原子写入**："写临时文件→fsync→`Path.replace()`"（参考
   `tushare_fundamentals.py` 的 `_write_cache`），裸 `open("w")` 覆盖写在
   多进程环境下会让另一个进程读到截断文件。

## 安全红线（不能碰的）

- `TUSHARE_TOKEN` 禁止硬编码，优先级：构造参数 > 环境变量 >
  `~/a-stock-tracker/.env`（`read_tushare_token()`，路径可用 `env_path` 覆盖）。
- 第三方 SDK（tushare/baostock）import 必须懒加载在方法内部，构造函数保留
  `client` 注入参数，测试不能碰真实网络。
- 不能裸 `raise Exception`，失败路径统一收敛成
  `MarketDataResult(status="failed", error_code=...)`。
- 不能直接改 `~/a-stock-tracker/` 内代码——该仓库有未提交改动，没用户明确
  授权前禁止碰。
- 不提交 `.env`/密钥/凭证/临时文件。

## 项目现状（2026-07-21）

源码版本 `0.4.0`。已实现 TuShare 估值、财务、分红 Provider、十年估值分位计算、
统一限流/错误语义和默认凭据隔离；库级基线为 `155 passed`。0.4.0 wheel 已通过
tracker `964 passed`、research `490 passed` + bash `6 passed` 的隔离 shadow，
但尚未安装到生产消费者。

跨项目当前状态：a-stock-tracker 仍锁定 `a-stock-lib==0.2.0`，research 仍使用
`0.3.0`；后续 cutover 需单独确认。Phase 6 仍保持
report-only；2026-07-02 已把 weekly PM loop 自动化为每周一 09:30 cron，检查
weekly/daily/outcome 日志、`READY_CRON` 和 `accuracy-report`，并通过 Telegram bot
发送摘要（tracker commit `f181010`，验证 `211 passed, 1 skipped`）。该任务已经按
"涉及 cron/Telegram 必须单独确认"的边界写 spec、经 agy 独立审查 PASS 后实现并
安装 crontab。

`collab-retro` 刚新增"状态文档对齐检查"（Output 1b，config 的
`project.status_files`），本项目已声明 `CLAUDE.md`/`AGENTS.md`/`README.md` 三个
文件启用它——以后跑 `collab-retro` 时它会自动检查这三个文件的"当前状态"段落是否
过时，你不用再靠人工发现。

当前明确遗留项：a-stock-research 的 PM/agent CLI 数据库路径防呆仍待设计，原因是
历史上绕开 pytest 的 CLI smoke test 误写过生产 `cache.db`。`cmd_checklist` 里 C
框架的 warn-only 提前反馈 UX 已于 2026-07-02 在 research 侧完成，不再是遗留项。

## 文档指针

- 项目为什么这么设计 → `docs/design/2026-06-22-three-system-restructure-design.md`
- 任务拆解/验收标准 → `docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`
- 历史变更 → `CHANGELOG.md`（每个阶段结束都有"执行复盘"小节，记录审查发现了
  什么、哪些是真 bug 哪些是虚警——这些判断依据比结论本身更值得读）
- 跨 agent CLI 通用约束 → `AGENTS.md`（内容等价于 `CLAUDE.md`，去掉了 Claude
  专属表述，这是你应该重点读的那份）
- ai-collab 三方协作流水线机制本身 →
  `/home/lin/.claude/skills/ai-collab/design.md` + 各 `collab-*/SKILL.md`
- 过去的方向性决策记录（含分歧/收敛的完整论证）→
  `.claude/ai-collab/state/decisions.jsonl`

## 一句话总结

你现在既要写代码，也要替我做判断——判断的具体尺度是：能自己验证清楚的，自己
验证完再动手；碰不准、影响范围大、或者本来就该问用户的，停下来问，不要为了
"看起来完成了"而囫囵吞枣。
