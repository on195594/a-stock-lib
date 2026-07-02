# contract parser 容错策略

日期：2026-07-02
状态：accepted strict-v1
适用范围：`a_stock_lib.contracts` 的主观分项标签与周期位置标签解析器

## 结论

当前 `0.2.0` parser 继续保持严格 fail-closed，不扩大容错范围。

支持：
- 标签可出现在较长 Markdown 正文中。
- 标签 body 首尾空白可忽略。
- 分隔符可用中文分号 `；` 或 ASCII 分号 `;`。
- `阶段` 值和 `评级`/`置信度` 值首尾空白可忽略。
- 证据和依据文本内可包含换行、方括号等普通正文字符。

不支持：
- 中文全角引号 `“ ”`。
- 全角方括号、圆括号或其他替代标签边界。
- 字段乱序，例如先 `依据` 后 `阶段`。
- 字段名、等号、分隔符周围的任意空格变体，例如 `阶段 = 上行期`。
- 证据列表不用 ASCII 双引号包裹。
- 同一周期位置标签出现多次。

## 理由

这些标签是 LLM 输出到代码消费的 contract，不是自然语言抽取器。当前下游 `a-stock-research`
已经把 C/D/B 框架周期位置判断接成 fail-closed；如果 parser 默默接受过多变体，会降低提示词
格式约束的可观察性，也会让错误格式在报告里长期积累。

`prompts/fragments/subjective_evidence.md` 和 `prompts/fragments/cycle_stage.md` 已明确要求
ASCII 双引号，并把这点写成解析器硬约束。现阶段不应在 `a-stock-research` 本地补临时正则，
也不应在不更新 canonical prompts 的情况下放宽共享 parser。

## 变更规则

未来如确实要支持某种变体，必须按以下顺序执行：

1. 在本仓库更新本 spec，说明新增容错的业务理由和不支持的边界。
2. 修改 `a_stock_lib/contracts.py`，并补充对抗测试。
3. 若格式变更会影响 agent 输出，先更新 `prompts/` canonical 源，再用 `scripts/render_prompts.py` 同步下游。
4. 在 `a-stock-research` 只消费新版本共享 parser，不在本地维护分叉正则。

## 当前验证锚点

- `tests/test_contracts.py::test_parse_cycle_stage_tag_rejects_field_order_variation`
- `tests/test_contracts.py::test_parse_cycle_stage_tag_rejects_chinese_full_width_quotes`
- `tests/test_contracts.py::test_parse_subjective_assessment_tags_rejects_field_order_variation`
- `tests/test_contracts.py::test_parse_subjective_assessment_tags_rejects_chinese_full_width_quotes`
- `tests/test_contracts.py::test_contract_parsers_allow_brackets_inside_quoted_text`
- `tests/test_contracts.py::test_contract_parsers_allow_newlines_inside_quoted_text`
