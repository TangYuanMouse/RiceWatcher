# 邮件业务处理与 LLM 提示词设计

版本: v0.1
日期: 2026-04-29

## 1. 当前实现现状

当前仓库中:

- 已有网关循环和 run 事件流。
- 尚未接入真实邮箱协议层（IMAP/Gmail API）。
- 尚未实现邮件正文/附件解析、邮件分类、订单自动创建。
- 时间线模型支持 email 事件来源，但当前是样例数据。

这意味着现在是“框架可跑通”，但“邮件业务处理链”还没落代码。

## 2. 邮件处理完整流水线（建议落地）

### 阶段 A: 接收邮件

1. 定时拉取或 webhook 推送。
2. 为每封邮件生成 `message_uid` + `source_account` + `thread_id`。
3. 原始邮件保存到本地（eml/json），入库 metadata。

建议数据表:

- `email_accounts`
- `email_messages`
- `email_attachments`
- `email_tasks`

### 阶段 B: 预处理

1. MIME 解析（正文 plain/html、附件列表）。
2. 去签名、去历史引用、去模板噪音。
3. 语言检测（中/英）和字符集统一。
4. 附件文本提取（PDF/Docx/OCR 图像）。

输出统一结构 `EmailNormalized`:

- sender, recipients, subject, body_clean
- attachment_texts[]
- thread_context_summary

### 阶段 C: LLM 分类与信息抽取

先分类，再抽取，避免一个提示词过重。

1. 邮件分类（intent）
- new_inquiry
- quotation_reply
- order_confirmation
- payment_notice
- logistics_docs
- old_customer_followup
- non_business_spam

2. 字段抽取（structured JSON）
- 产品名/型号/数量
- 目标价/币种
- 交期、目的地、运输偏好
- 客户公司、联系人、职位
- 风险标记（低置信度字段）

### 阶段 D: 动作编排

按分类触发动作:

- `new_inquiry`: 创建线索 + 生成回复草稿
- `quotation_reply`: 更新报价上下文 + 生成谈判建议
- `order_confirmation`: 创建或更新订单
- `payment_notice`: 更新订单状态至待生产/生产中
- `logistics_docs`: 更新发货节点与单号

所有动作都写入 timeline 事件，并附 source=agent/email。

### 阶段 E: 人工确认与发送

默认规则:

- “写入型动作可自动执行”。
- “对外发送动作必须人工确认”。

例如:

- 自动: 创建订单草稿、更新客户阶段。
- 需确认: 发送报价邮件、发送催款邮件。

## 3. 与当前网关循环的对接方式

你现有网关里可把现在硬编码步骤替换为以下流水线节点:

1. `email_fetcher`
2. `email_preprocessor`
3. `email_intent_classifier`
4. `email_field_extractor`
5. `business_action_planner`
6. `timeline_writer`
7. `reply_drafter`
8. `approval_gate`

并继续沿用现有三类事件流:

- lifecycle
- tool
- assistant

## 4. LLM 提示词设计（核心）

提示词建议拆成三层:

- System Prompt: 稳定规则与约束
- Task Prompt: 当前任务目标
- Output Schema Prompt: 强制结构化输出

### 4.1 System Prompt（全局）

你是外贸业务邮件分析助手。你的任务是将邮件内容转成可执行的结构化业务信息。

硬性规则:

1. 不得编造邮件中不存在的事实。
2. 信息不确定时输出 `null` 并给出 `confidence`。
3. 所有金额必须保留原币种。
4. 不直接执行对外发送动作，只产出建议和草稿。
5. 输出必须符合给定 JSON Schema，不要输出额外文字。

### 4.2 邮件分类 Prompt

任务: 根据邮件正文和附件摘要进行业务分类。

可选标签:
- new_inquiry
- quotation_reply
- order_confirmation
- payment_notice
- logistics_docs
- old_customer_followup
- non_business_spam

输入:
- subject
- sender
- body_clean
- attachment_summaries

输出 JSON:
{
  "intent": "new_inquiry",
  "confidence": 0.0,
  "reasons": ["..."],
  "need_human_review": false
}

### 4.3 字段抽取 Prompt

任务: 从邮件中抽取询盘或订单核心字段。

字段:
- product_items[]: {name, model, quantity, unit}
- target_price: {value, currency}
- destination_country
- incoterm
- lead_time_requirement
- payment_terms
- customer: {company, contact_name, title}

输出 JSON:
{
  "fields": { ... },
  "missing_fields": ["incoterm"],
  "confidence": {
    "product_items": 0.92,
    "target_price": 0.66
  }
}

### 4.4 动作规划 Prompt

任务: 依据 intent 与抽取字段，生成“系统内部动作计划”。

动作类型:
- create_lead
- update_customer_stage
- create_order_draft
- update_order_status
- draft_reply_email
- request_human_confirmation

输出 JSON:
{
  "actions": [
    {
      "type": "create_order_draft",
      "reason": "Detected order confirmation keywords and PO attachment",
      "risk": "medium"
    }
  ],
  "next_best_action": "draft_reply_email"
}

### 4.5 回复草稿 Prompt

任务: 生成可发送邮件草稿。

约束:

1. 不能承诺系统中不存在的库存或交期。
2. 遇到字段缺失时以提问方式补齐。
3. 语气专业、简洁，默认英文输出，可按来信语言切换。

输出 JSON:
{
  "subject": "...",
  "body": "...",
  "tone": "professional",
  "placeholders": ["lead_time", "payment_terms"]
}

## 5. 推荐模型调用策略

1. 分类模型: 小模型，低成本高吞吐。
2. 抽取模型: 中/大模型，确保字段准确。
3. 草稿生成: 可用中模型。
4. 同步返回分类结果，异步补充复杂抽取。

建议参数:

- temperature: 0.0 ~ 0.2（分类/抽取）
- temperature: 0.3 ~ 0.5（草稿）
- top_p: 0.9

## 6. 质量与安全控制

1. 置信度阈值
- 小于 0.7 自动标记人工复核。

2. 防越权规则
- 所有外发动作需审批。
- 高风险关键词（合同变更、退款、索赔）强制人工确认。

3. 审计
- 保存原始输入、提示词版本、模型响应、最终动作。

## 7. 最小可落地实现顺序（2 周）

Week 1

- IMAP 拉取 + MIME 解析
- 分类 Prompt + 结构化输出
- timeline 写入

Week 2

- 字段抽取 Prompt
- 动作规划 Prompt
- 回复草稿 + 审批 gate

完成后再接订单状态机与附件 OCR 深化。
