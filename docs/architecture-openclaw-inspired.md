# RiceWatcher 架构设计（OpenClaw 风格）

版本: v0.1
日期: 2026-04-29

## 1. 设计目标

本架构以 OpenClaw 的核心思想为蓝本，并针对外贸业务进行约束化落地:

- 单一网关进程作为系统事实源，统一消息入口、会话路由、任务调度和工具调用。
- 每个客户会话串行执行，避免订单/邮件/时间线并发写入冲突。
- 事件流优先，所有 Agent 执行过程可被前端实时订阅。
- 多 Agent 分工，但共享统一数据模型与权限策略。
- 默认本地优先，离线可用，联网能力按模块渐进开启。

## 2. 逻辑分层

1) Interaction Layer
- Web 控制台
- 移动消息通道适配层（后续接 Telegram/飞书）

2) Gateway Orchestration Layer
- Gateway API
- Session Lane Queue
- Agent Router
- Tool Policy + Approval
- Task Flow Scheduler

3) Domain Engines
- Product Research Engine
- Lead Discovery Engine
- Unified Inbox & Order Engine
- Customer Timeline Engine

4) Memory & Data Layer
- Transaction DB（PostgreSQL/SQLite）
- Vector Memory（Qdrant/Chroma）
- File Vault（附件、报价单、日志）

## 3. OpenClaw 风格关键模式映射

### 3.1 Single Gateway Source of Truth

- 所有请求统一进入 Gateway。
- 网关负责会话选路、权限判定、执行状态机。
- 前端不直连业务引擎，避免绕过审计。

### 3.2 Session Lane Serialization

- 每个 session_key 对应独立执行锁。
- 同一会话内任务按顺序执行。
- 防止邮件解析、订单状态推进、时间线写入互相覆盖。

### 3.3 Agent Loop + Event Streaming

- agent run 分三类流事件:
  - lifecycle: start/end/error
  - assistant: 文本增量
  - tool: 工具调用状态
- 网关先返回 accepted，再由事件流持续返回执行过程。

### 3.4 Multi-Agent Routing

建议四个主 Agent:

- research-agent: 选品和趋势分析
- lead-agent: 潜客搜索与破冰建议
- inbox-agent: 邮件解析、询盘提取、报价建议
- timeline-agent: 客户叙事链与跟进建议

### 3.5 Task Flow（持久化工作流）

任务不是一次调用，而是可追踪流程:

- 例: 每周选品简报
  - preflight
  - collect
  - summarize
  - approve
  - deliver

### 3.6 Security Baseline

- 默认本地绑定和 token 鉴权。
- DM/多人场景按 sender 隔离会话。
- 高风险工具默认 deny，需审批放行。
- 严格区分“能触发机器人”和“能触发哪些工具”。

## 4. 数据与事件主线

用户指令 -> Gateway -> Session Lane -> Agent Router -> Tool Calls ->
Structured Write(DB/File/Vector) -> Event Stream -> UI Timeline

## 5. 可演进路线

Phase A（当前）
- 本地 Web + 单网关 + 基础会话串行 + 模拟工具流

Phase B
- 接入真实邮件源（Gmail/IMAP）
- 加入订单状态机和报价单生成

Phase C
- 引入多通道消息入口
- 增强审批和审计
- 自动化定时任务与失败重试
