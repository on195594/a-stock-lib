# A股投研三系统重构设计（已批准且已全面落地）

日期：2026-06-22
最近状态更新：2026-07-01
范围：`a-stock-tracker`（独立仓库，35支自动评分管道）/ `a-stock-research` skill（新股研究）/ `a-stock-monitor` skill（持仓监控）
状态：**架构方案已获用户批准且已全面落地**。Phase 1-4 均已执行完成；后续技术债清理、`contracts.py` + `prompts/` canonical 源、Phase 3b 周期位置结构化校验接线也已完成。当前本仓库版本为 `0.2.0`，全量测试 `92 passed`。`a-stock-tracker` 已切至本包 Provider（当前仍锁定 `a-stock-lib==0.1.3`，尚未升级到 `0.2.0`）；`a-stock-research` 已安装并消费系统 Python 中的 `a-stock-lib==0.2.0`。

---

## 1. 三系统现状摘要

### 1.1 a-stock-tracker（独立仓库）

5173行Python，分层清晰：`lib/fetcher.py`(数据获取) → `lib/cache.py`(SQLite存储) → `scorer.py`(Framework A定量评分) + `gemini_scorer.py`(定性评分) → `pipeline.py`(编排) → `telegram_push.py`/`sheets_sync.py`(输出)。

- **数据流**：每周六抓基本面 → 工作日16:30评分写`predictions`表 → 17:00回填30/60/90日实际涨跌算alpha（SQLite GENERATED COLUMN自动算）→ `accuracy-report`统计命中率
- **行情数据**：Tushare为主源（`lib/tushare_provider.py`，需`TUSHARE_TOKEN`），BaoStock降级fallback，AKShare行情已禁用。**基本面仍依赖AKShare，无provider抽象**（CLAUDE.md明确写"未受此次迁移影响"）
- **跟两个skill的关系**：`lib/fetcher.py`/`lib/cache.py`最初从`a-stock-research`复制，已分叉演进2个月，数据互不相通

### 1.2 a-stock-research skill

WebSearch+LLM对话驱动的新股研究工具。`fetcher.py`拉结构化数据（6个AKShare接口，5稳定/1不稳定）→ `cache.py`（SQLite）→ SKILL.md定义6套行业框架打分规则（基本面60+择时20=80分）。已完成一轮小修：框架决策持久化到`analysis_results.framework`，主观分项加文字证据要求，industry接口失败时复用历史缓存。**这份skill目录没有`.env`/token机制，是纯文字+脚本目录，不是独立git项目**。

### 1.3 a-stock-monitor skill

持仓后管理：止损/止盈/L1-L2-L3论点记录/12个月复查。复用`a-stock-research`的`cache.py`，逻辑全部是SKILL.md文字规则。

---

## 2. 踩过的坑（按系统归类）

### a-stock-tracker
| 坑 | 根因 | 状态 |
|---|---|---|
| gross_margin全NULL 4天 | fetcher的web数据源占位未实装 | 已修复 |
| pb_percentile月度静态导致评分多日相同 | 只在weekly更新 | 已修复（改daily内存计算） |
| spot_em接口系统性不稳定但被计入"成功" | 降级fallback掩盖真实失败率 | 未修复，记录在案 |
| cron静默失败2个月 | PATH错误导致告警链路本身断掉 | 已修复 |
| `market_data.py`的Provider协议硬`import lib.cache`写audit | 设计时没考虑跨项目复用 | 本次重构需解耦（见第5节） |

### a-stock-research / a-stock-monitor
| 坑 | 根因 | 状态 |
|---|---|---|
| dps/股息率虚高50-65% | 滚动366天窗口跨财年叠加 | 已修复（改按报告期分组） |
| net_profit_growth"反复出错"（3起案例） | 不是bug，字段是3年均值，被误拿单年同比对照 | 已翻案 |
| 煤价搜索混入沫煤/焦煤数据 | WebSearch笼统搜索易命中错误煤种 | 已强化memory提醒 |
| add-holding每次INSERT新行 | 缺UPDATE/UPSERT语义 | 未根治，靠手动UPDATE绕过 |
| 止损系数全框架统一15%/20% | 没区分波动率差异 | 已按框架差异化 |
| 框架推断靠industry关键词反推，industry常是AKShare失败占位文本 | 框架本该在分析时已显式决定，下游又用脆弱字符串重猜 | 已改为持久化+兜底降级 |
| 主观分项凭印象打高分 | 无可验证证据要求 | 加了文字规则，但**只是软约束，无脚本强制**——本次方案2要解决的正是这类问题 |

### 跨系统
- 2026-06-14已审查"两套心跳要不要合并"，结论：research(5支持仓)和tracker(35支扫描)标的池和职责本质不同，**不该合并业务逻辑**。本次重构延续这个结论：三系统继续水平切分，只共享底层数据/引擎代码。

---

## 3. 值得保留的设计

**a-stock-tracker**：
- Provider抽象（primary/fallback协议化，迁移Tushare时只改provider实现、上层零改动）
- audit trail（market_data_audit表记录每次调用source/status/fallback_reason）
- all-or-nothing fallback（Gemini定性评分整体命中或整体退回固定值）
- SQLite GENERATED COLUMN算alpha
- weights_hash可复现性追踪机制

**两个skill**：
- 双轨评级矩阵（配置评级×时机评级→仓位建议）
- 周期前置检查（C/D/B框架强制先判断周期位置再打分，今天补上ROE折扣）
- 防韭菜检查清单思路（结构化但目前是纯文字）

---

## 4. 多Agent执行环境澄清（本次讨论中纠正的关键认知）

讨论中途澄清：**`agy`和`hermes`不是Claude子agent，是本机两个独立装的agent runtime**：
- `agy` = Google Antigravity CLI（`/home/lin/.local/bin/agy`独立二进制）
- `hermes` = 另一个独立agent runtime（`~/.hermes/`，自带provider fallback、telegram/webhook发送能力）

**这条澄清改变了原本的优先级判断**：分析执行层要在claude/agy/codex之间切换、交互面可能是hermes telegram或claude telegram，**这是近期要落地的真实需求，不是远期假设**。SKILL.md这类"只有Claude技能机制能解读的文字规则"对agy/codex无效——它们读不到、也不保证以相同方式解读这套规则。这直接把"评分逻辑确定性化"的优先级从"分层架构里的一条建议"提升为"多后端一致性的硬需求"。

---

## 5. 独立对抗审查（agy / Google Antigravity CLI）与实测验证

设计方案2获批后，用真实的`agy` CLI（非Claude子agent，`--model "Gemini 3.1 Pro (High)"`）对本文档做了一轮红队审查，4条发现+实测验证结论如下：

| agy发现 | 评估 | 处理 |
|---|---|---|
| 共享包若用`sys.path.append`引用，沙盒/容器化场景会找不到包；无版本锁定，tracker改包会直接冲击两个skill | **采纳** | 5.1改为`pip install -e`+版本约束，不用路径注入 |
| "入参错觉"：打分公式确定性了，但喂给公式的数字如果是LLM从原文读出来的，不同backend读法仍不同，只是把"打分不一致"换成"读数不一致" | **采纳，明确范围边界** | 5.3新增"输入来源分类"，诚实标注方案2只解决公式层一致性 |
| Tushare`stock_basic`的行业分类口径可能跟AKShare/东财不是同一套体系，换源后框架路由关键词大面积失配；tracker(35支)和skill共用同一120积分token可能撞免费档限流 | **已实测，结论比担忧的轻** | 见5.2实测结果 |
| 试点选`C资源`+`A通用`两个量化指标最多、最容易代码化的框架，会有幸存者偏差，掩盖`E消费`/`F科技`这类靠定性叙事的框架真实迁移难度 | **采纳** | 5.3试点集补充`F科技`（最依赖定性判断的框架） |

### 5.2 实测：Tushare `stock_basic` 可行性验证

用tracker现有`TUSHARE_TOKEN`实际调用`stock_basic`，对比当前`a-stock-research`缓存里25个已抓取代码的industry字段：

- **调用性能**：1.61秒返回全市场5528行，验证"一次性批量缓存、非高频调用"的设计前提成立——tracker(35支)和skill(任意股票)都只需偶发刷新本地缓存，不存在并发抢占同一token配额的场景，agy担忧的限流场景在此用法下不成立
- **分类口径对比**（25支样本）：
  - 多数语义一致或Tushare更准确：比亚迪"汽车整车制造(新能源汽车)"→"汽车整车"，东方电缆/中国神华此前AKShare从未成功过（"未知"），Tushare给出"电气设备"/"煤炭开采"——稳定性确认提升
  - 1处表述差异需要适配：长江电力AKShare"水电公用事业" vs Tushare"水力发电"，`infer_framework`的关键词匹配若依赖"水电"精确字符串会失配，需要扩充关键词表
  - **1处疑似数据质量问题**（agy的风险方向被证实是对的，但根因不同）：北方稀土AKShare显示"钢铁"（明显错误，北方稀土是稀土生产商），Tushare给出"小金属"（更准确）——说明AKShare残留数据本身可能有错，迁移时要做新旧值差异清单人工核对，**不能假设旧数据源是正确基线**
- **结论**：换源可行，但Phase 2必须先跑一次全量差异对比（新旧industry值并排输出），人工过一遍而不是静默切换

## 6. 最终架构决策

### 6.1 新建共享包 `~/a-stock-lib/`

独立于`a-stock-tracker`和两个skill的第三方位置，三者都通过这个包获取数据/评分能力，但**不合并业务逻辑**（延续06-14结论）——共享的是底层能力，不是研究/监控/扫描各自的决策流程。

物理迁移`lib/market_data.py`的Provider协议设计（`MarketDataResult` dataclass + 统一错误码常量 + Protocol接口）到此包，**解耦其对`lib.cache.insert_market_data_audit`的硬import**，改为调用方注入的回调（audit写入逻辑留在各自项目自己的cache.py里，包本身不绑定任何项目的数据库schema）。

**引用方式（第二轮agy工程审查纠正，推翻第一轮的提法）**：第一轮提出的`pip install -e`是对editable install的误用——`-e`本质是源码软链接，任何未commit的改动会**立刻无条件**在所有引用环境生效，完全起不到"版本锁定"作用，反而是风险集中的放大器（单人维护时为修skill侧小bug改了lib代码，会瞬间连带影响tracker生产环境）。

改为**真正的版本化安装**：`a-stock-lib`用`python -m build`打成wheel，每个消费方（tracker/research/monitor）各自的`requirements.txt`/等价文件锁定到具体版本号（如`a-stock-lib==0.2.1`，从本地路径/简单文件索引安装，不需要发布到PyPI）。改`a-stock-lib`代码后必须显式bump版本号、重新build，各消费方再显式升级依赖版本——不会有"改了源码立刻所有消费方一起生效"的隐式风险。禁止用`sys.path.append`这类路径注入，同样会绕开版本管理。

### 6.2 基本面数据provider扩展

新增Tushare `stock_basic`接口作为a-stock-research的industry数据源（替代不稳定的AKShare `stock_individual_info_em`），已通过5.2节实测验证可行：
- 120积分（注册即送的免费档）即可调用，一次性拉全市场~6000支股票industry字段，缓存到本地，非高频调用
- Token**直接读取`~/a-stock-tracker/.env`里的`TUSHARE_TOKEN`**，不在skill侧重复配置密钥
- AKShare原有5个稳定接口（财务指标/分红/股价历史/PB/国债）保留不动，只替换这一个不稳定接口
- **Phase 2实施时必须先跑全量新旧industry值差异对比并人工过一遍**（5.2节发现北方稀土这类旧数据本身有误的案例），不能静默切换
- tracker自己的基本面层（目前同样裸用AKShare无provider抽象）后续接入同一套provider协议，两边收益是一致的

### 6.3 评分引擎确定性化（已批准方案2，范围已明确边界）

把SKILL.md里6套行业框架的打分公式、周期前置检查的量化阈值，逐步转译成`a-stock-lib`里的确定性代码（参照tracker的`scorer.py`+`weights.json`模式，包括`weights_hash`可复现追踪机制）。

**输入来源分类（吸收agy的"入参错觉"意见，明确方案2的真实解决范围）**：
- **API结构化数字**（ROE/PE/PB/股息率/营收增速等，来自provider层）：方案2能保证这部分多后端100%一致，不受LLM读法影响
- **LLM从原文/WebSearch提取或判断的部分**（护城河强弱、管理层质量、行业地位等叙事性输入）：**方案2不解决这部分的跨backend一致性**，这是诚实的边界，不是被掩盖的缺陷。这部分继续靠SKILL.md的证据门槛软约束，多后端之间允许存在解读差异
- 文档/SKILL.md后续要明确标注每个打分项属于哪一类，让"调引擎拿分"和"LLM主观判断"的边界对维护者可见
- **"LLM主观判断"这一类具体怎么交给代码消费，见6.6 Contract层**——不是停在"诚实标注没法保证一致"就结束，而是用typed contract让这部分至少有结构化校验，即使不同backend的判断内容不同，格式和证据要求是统一强制的

**落地方式：分批试点，不是一次性迁移6个框架**。试点集扩展为三个框架（吸收agy"幸存者偏差"意见）：`C资源`（波动最大、最依赖周期前置检查）、`A通用`（覆盖面最广）、**`F科技`（最依赖定性叙事判断，专门用来测试"主观输入占比高的框架"代码化的真实难度，避免只测好测的框架得出过于乐观的工作量估计）**。三个框架试点完成、对比"代码化打分 vs LLM现行打分"结果一致后，再决定要不要推全部6个。

### 6.4 多Agent职责分工

维持水平切分（tracker/research/monitor三个独立闭环），不引入运行时多agent协作。**踩坑知识和底层能力通过`a-stock-lib`跨系统复用**（这正是本次重构要解决的事），但各系统的决策流程、标的池、运行节奏继续独立。

### 6.5 Prompt/指令层独立分层（已批准方案I）

第三层架构决策：在Provider层、评分代码层之外，新增`a-stock-lib/prompts/`作为canonical来源，存放"代码化不了、必须靠LLM执行"的指令文字（框架识别引导、证据校验提示词、报告措辞规范）。写一个轻量渲染脚本，从这份canonical源生成各backend需要的指令文件格式：
- Claude：渲染成`SKILL.md`（通过Skill工具加载）
- agy/codex/hermes：渲染成`AGENTS.md`

**已实测验证agy会自动读取AGENTS.md**：在工作目录放一个内嵌暗号的`AGENTS.md`，不在prompt里提及该文件，要求agy做自我介绍——回复主动带出暗号，证明`agy --add-dir`确实会自主发现并加载该文件，不需要显式告知。这条原本是开放问题，现已闭环，方案I的前提成立。

Prompt内容单独维护一个版本号（`prompt_hash`，跟评分代码层的`weights_hash`机制对齐但分开追踪），调整措辞/打分提示策略只改`prompts/`源文件+重跑渲染脚本，不需要碰`a-stock-lib`里的Provider/评分代码，两层改动互不牵连。

落地顺序：Phase 1建共享包骨架时，先把现有SKILL.md里"必须靠LLM执行"的部分抽出来放进`prompts/`canonical源（先验证抽取后能重新生成等价的SKILL.md，不丢内容），再补AGENTS.md渲染输出供agy/codex/hermes使用。

### 6.6 Contract层（第一性原理自查后新增，弥补6.3的遗留缺口）

用户提出的架构原则（"LLM负责理解/路由/解释，代码负责事实/执行/验证"）做自查后，发现6.3节"输入来源分类"只分了两类（API结构化数字 / LLM主观判断），但没有规定**LLM主观判断怎么交接给代码**——现状是自然语言报告→代码用正则在原文里扫关键词，这正是用户原则里明确点名的反模式（"LLM输出自然语言→正则提取字段→业务逻辑继续执行"）。

**具体证据（已实测确认，不是假设）**：`a-stock-research/cache.py`里已经实现并在用的`validate_subjective_evidence(report_text: str) -> list[str]`，对护城河/行业地位等4类主观分项，是在整段报告原文里用正则找"[强/优]方括号标记+附近是否有证据关键词"，曾经因为裸字符匹配误判"护城河不强"里的"强"字而修过一次bug。`周期位置判断`（C/D/B框架必做的第1.5步）现状更原始：SKILL.md里只是"[在此填写判断结果及依据]"的填空，判断结果只活在报告文字里，从未被解析成代码能读的结构化字段。两者都是同一类缺口：**LLM的主观判断没有typed contract，代码只能在原文上做脆弱的字符串匹配，不是在结构化对象上做schema校验**。

**新增设计**：在`a-stock-lib`里新增`contracts.py`，给所有"LLM输出→代码消费"的边界定义dataclass/enum：
- `FrameworkDecision`（框架决策，enum约束，现状已基本符合，正式收编进contracts.py）
- `CycleStageAssessment`（周期位置判断，enum：上行/顶部/下行/底部 + 依据文本字段，新增——替代现在的"填空"）
- `SubjectiveAssessment`（护城河/行业地位/特许经营稀缺性/品牌渠道，每类一个`{rating: enum, evidence: list[str], confidence: enum}`，新增——替代现有的正则扫描）

**初版"报告末尾追加JSON块"的方案已被agy对抗审查否决，不采用**：agy指出两个新洞——①JSON块跟报告正文物理脱节后，LLM可以在正文完全没分析的情况下在JSON里编造"近3年市占率提升"之类的假证据，schema校验只查"非空"查不出真假，反而比现有正则更容易被糊弄（现有正则至少要求证据关键词出现在评级附近的叙述里，是个弱但有效的反编造proxy，JSON尾块会丢掉这个属性）；②claude/agy/codex三个backend输出JSON的习惯格式不同（带不带markdown代码块标记、引号风格等），严格`json.loads`校验会把格式细节误杀成"显式拒绝"，伤及语义正确的报告。

**修正方案**：不引入JSON块，证据继续内嵌在报告叙述里（保留"物理紧邻"这条弱防编造proxy），但把现有"宽松扫描评级附近2-3行任意证据关键词"收紧成强制的内嵌结构化标记语法，例如`护城河[评级=强；证据="近3年提价但销量未降，市占率连续5年第一"]`——代码用简单确定的正则/小parser校验这个紧凑格式是否存在、`证据`字段是否非空，比现有"评级标记+附近若干行任意关键词命中"的宽松启发式更不容易误判，同时不依赖JSON、不引入跨backend格式解析问题。

**已知限制（写明不回避）**：无论是旧的正则方案还是这次收紧后的内嵌标记方案，**都无法验证证据的真实性**，只能强制"必须提供格式正确、非空的证据条目"——这是格式校验层能做到的上限，"证据是否属实"需要跟WebSearch/API结果交叉核对，那是另一个更大的verification问题，不在这次retrofit范围内，留作已知限制。

**这条不只是设计文档层面的事，`validate_subjective_evidence`是已经写好并在用的代码**——退一步评估优先级：agy建议完全推迟到"客观评分引擎稳定后"才做，我不完全同意，因为修正后的方案只是"收紧一个函数的语法要求"，改动范围很小，不需要等Phase 1的Provider/评分代码工作全部做完。结论：**这个小修可以独立先做或在Phase 1内作为单独子项**，不与`contracts.py`里另外两个新typed对象（`CycleStageAssessment`等，范围更大、需要新设计）绑死在一起。

---

## 7. 实施路线图（高层，详细步骤留给实施计划）

**顺序已按第二轮agy工程审查重排**：原计划Phase 1直接动tracker现有生产代码（"迁移"=物理剥离），agy指出这是"切断大动脉原地手术"——tracker每天16:30有daily cron在跑生产评分，且历史上已经发生过cron静默失败2个月没人发现的真实事故（见第2节），不该让风险最高、7x24自动运行的系统第一个承担新包不稳定的风险。改为**复制不挪走、skill先趟雷、tracker最后切**的顺序：

1. **Phase 1 — 共享包骨架（tracker零风险敞口）**：新建`~/a-stock-lib/`，**复制**（不是移动/删除）tracker现有`market_data.py`的Provider协议代码进去并解耦audit硬编码，加Tushare `stock_basic` fundamentals provider；同步把SKILL.md里"必须靠LLM执行"的部分抽成`prompts/`canonical源+渲染脚本；新增`contracts.py`定义`FrameworkDecision`/`CycleStageAssessment`/`SubjectiveAssessment`。**tracker此时不改一行代码，继续用自己原有的`lib/`跑生产，无任何风险敞口**
2. **Phase 2 — skill侧先接入，当真实验证场**：a-stock-research/monitor（手动触发、容错率高，不是7x24自动运行）率先把`fetcher.py`换成调用`a-stock-lib`的fundamentals provider；**先跑全量新旧industry值差异对比并人工核对**（5.2节发现的数据质量问题不能静默带过）；同时在这个阶段做`C资源`/`A通用`/`F科技`评分引擎试点、`validate_subjective_evidence`的语法收紧retrofit——用风险更低的系统把新包里的坑先趟完

   **⚠️ 2026-06-23实际执行范围已收窄（用户决定）**：本节描述的Phase 2原计划把"行业Provider替换"和"评分引擎试点"/"证据语法retrofit"绑在一起；实际执行时拆分为：①②(行业Provider替换+diff核验，仅`a-stock-research`，已完成，见README)单独执行；评分引擎试点、证据语法retrofit**改为独立任务分别单开**，不在本次Phase 2范围内。另外，`validate_subjective_evidence`这个函数本身**已经在06-22 commit`421fe2c`里直接实现并上线**（在`a-stock-research`自己的`cache.py`，不经过`a-stock-lib`），这里提到的"retrofit"如果还要做，应理解为"对已上线版本做进一步语法收紧"，不是从零实现。**`a-stock-monitor`接入情况（06-23已查明并处理）**：`a-stock-monitor`没有自己的代码，只有`SKILL.md`，所有数据操作都是直接shell调用`a-stock-research`的`cache.py`/`fetcher.py`——上面这句"a-stock-research/monitor率先把fetcher.py换成调用a-stock-lib"对monitor而言是错误假设，没有独立fetcher可改。实际处理方式：核实monitor的5支持仓在`stock_fundamentals`表里的industry缓存（3支仍是改代码前写入的旧占位符），重新跑`fetcher.py fetch`刷新这5支，确认`portfolio-risk`输出后5支框架推断均无低置信度"?"标记。这不是代码改动，是数据刷新。
3. **Phase 3 — 共享包打磨**：根据Phase 2暴露的问题修`a-stock-lib`，此时tracker仍未接入，不受影响

   **2026-06-25更新**：Phase 3 的本包侧硬化已完成并提交（`f51d081 fix: 完成Phase3共享包硬化`），版本升至 `0.1.1`。已覆盖：primary/fallback 双失败信息保留、`MarketDataResult.error_code` Literal 收束、bars 非 DataFrame/缺列校验、`time limit exceeded` 归类为 `TIMEOUT`、Tushare 报价 Provider token 来源统一、BaoStock 登录/查询/代码转换异常屏障。全量测试 `44 passed`，wheel 构建和 scratch venv 安装 smoke 均已验证。按仓库约束，`~/a-stock-tracker/lib/` 未修改；tracker 侧同类预存缺陷仍需在 Phase 4 切换前单独同步处理。

   **Phase 3硬化清单（2026-06-23 Task2实施时agy审查发现，2026-06-25本包侧已完成）**：以下4处问题逐行核对后确认**均为tracker `lib/market_data.py`现有生产代码的预存缺陷**，Task2按"先复制不改动"原则原样搬运进`a_stock_lib/market_data.py`，未在搬运时顺手修——避免迁移窗口内新旧包行为出现未经验证的偏差。当前 `a-stock-lib` 已修复；tracker 本体仍未修改，后续 Phase 4 前需要同步评估：
   - `CompositeMarketDataProvider._fetch`（双方均在`fetch`方法内）：primary和fallback都失败时，直接`return fallback_result`，primary的真实失败原因（如Token失效）被静默吞掉，只剩fallback的报错，排查方向会被带偏
   - `normalize_bars_result`/`_normalize_bars_result`：非`l3_bars`场景只校验`date`/`close`两列，`open`/`high`/`low`缺失不会被拦截，下游若依赖这些列做计算会在更深的调用栈里抛`KeyError`而非在边界处收敛成`MarketDataResult("failed")`；另外入参非`pd.DataFrame`（如上游意外返回list/dict）时`getattr(df, "empty", False)`不会拦截，会在`.rename()`处抛未分类异常
   - `exception_result`/`_exception_result`：错误分类用纯子串匹配，`"time limit exceeded"`会被`"limit" in lowered`误判成`RATE_LIMITED`而非`TIMEOUT`，调用方可能因此做错误的退避重试决策
   - `MarketDataResult.error_code`类型标注是裸`str | None`，未用`Literal`收束到实际的错误码常量集合，类型检查器无法防拼写错误

   **追加（2026-06-23，agy编码规范体检发现，2026-06-25本包侧已完成）**：以下问题已逐行核对确认均为tracker `lib/tushare_provider.py`/`lib/baostock_provider.py`现有生产代码的预存缺陷。当前 `a-stock-lib` 已修复；tracker 本体仍未修改，后续 Phase 4 前需要同步评估：
   - `tushare_quotes.py:39`（`self.token = os.environ.get("TUSHARE_TOKEN") if token is None else token`）：与`tushare_fundamentals.py`的`read_tushare_token()`读`.env`文件的方式不一致，tracker原有的运行环境靠外部把`TUSHARE_TOKEN`导出成真实环境变量，三个provider的token来源没统一
   - `baostock_quotes.py:115`（`login = client.login()`）：在`try`块（126行起）之外执行，登录阶段真实抛出的异常（非baostock返回的`error_code`字段，而是Python异常）不会被收敛成`MarketDataResult("failed")`，会直接冒泡给调用方
   - `baostock_quotes.py:103`（`to_baostock_index_code(symbol)`）：在进入`_fetch_bars`内部统一`try`块之前调用，非法`symbol`触发的`ValueError`不会被转译
   - `baostock_quotes.py:_fetch_bars`（105-157行，53行）：超出函数≤50行的规范，混合了懒加载导入/登录鉴权/抓取/finally清理4类职责，建议拆出`_ensure_login()`私有方法
4. **Phase 4 — tracker切换（放在最后，不是第一步）**：只有共享包被skill侧验证足够稳定后，才让tracker把本地`lib/market_data.py`/基本面fetcher换成调用`a-stock-lib`，退役本地副本；同时决定要不要推全部6框架

   **2026-06-26更新**：Phase 4 已执行完成。`a-stock-tracker` 成功将本地 Provider 逻辑退役，切换并锁定消费 `a-stock-lib==0.1.2` 版本。在此期间，针对 BaoStock SDK socket hang 的主进程挂死风险，已加固开发了基于子进程隔离超时的 `IsolatedBaoStockMarketDataProvider` fallback 行情源，并完成 `0.1.2` 构建、全量测试（`48 passed`）与 scratch venv 安装 smoke 验证。

---

## 8. 自检清单

- [x] 无遗留TBD/占位段落
- [x] 第4节澄清后，第6节决策与之前讨论中的"初步倾向"段落已完全替换，不存在新旧结论矛盾并存
- [x] 范围聚焦：本文档只覆盖"共享包该建什么、评分引擎该不该代码化"两个已拍板的架构决策，不包含逐文件改动清单（留给实施计划）
- [x] 关键决策（token共享方式、共享包做法A/B、架构方案1/2/3）均标注用户的明确选择，非我单方面假设
- [x] 第5节agy对抗审查的4条发现均有对应处理（采纳/实测验证），不是走过场记录
- [x] 第6.3节明确标注方案2的范围边界（只解决API结构化输入的一致性，不解决LLM主观判断的一致性），避免过度宣称
- [x] 第6.5节Prompt层方案I的前提（agy会自动读取AGENTS.md）已实测验证，不是未经核实的假设
- [x] 架构最终是三层（Provider层/评分代码层/Prompt层）而非最初讨论的两层，第6节四个子节命名和实施路线图均已同步，不存在"文档说三层但路线图只提两层"的遗漏
- [x] 用户提供的"代码负责确定性"原则已逐条自查：已对齐的部分（Provider层typed Result+错误码、框架决策enum持久化）和未对齐的部分（`validate_subjective_evidence`正则扫描原文、周期位置判断纯填空无结构化字段）均已识别，6.6节给出Contract层方案，不是走过场引用
- [x] 6.6节初版"JSON尾块"方案经agy对抗审查发现2个新缺陷（脱节造假/跨backend格式脆弱）后已撤回并改为"内嵌结构化标记"修正方案，文档内无残留的JSON块描述（已grep确认），新旧结论不矛盾共存
- [x] 第二轮agy工程视角审查发现`pip install -e`版本锁定描述自相矛盾（editable install本身就是无版本锁定的软链接）+ Phase顺序让生产风险最高的tracker第一个承担新包不稳定风险，6.1节和第7节均已重写为"版本化安装+复制不挪走+skill先趟雷+tracker最后切"，不是简单追加一条意见
