from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


StreamType = Literal["lifecycle", "assistant", "tool"]
RunStatus = Literal["accepted", "running", "done", "error"]
OrderStatus = Literal["待确认", "待付款", "生产中", "待发货", "已发货", "已完成"]


class MessageIn(BaseModel):
    session_key: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)
    channel: str = "web"
    customer_id: str | None = None


class RunAccepted(BaseModel):
    run_id: str
    status: RunStatus = "accepted"
    accepted_at: str = Field(default_factory=utc_now_iso)


class RunEvent(BaseModel):
    run_id: str
    stream: StreamType
    phase: str | None = None
    content: str | None = None
    tool_name: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class RunInfo(BaseModel):
    run_id: str
    session_key: str
    status: RunStatus
    created_at: str
    ended_at: str | None = None


class Customer(BaseModel):
    id: str
    name: str
    country: str
    stage: str
    tags: list[str] = []


class TimelineEvent(BaseModel):
    id: str
    customer_id: str
    timestamp: str
    source: Literal["email", "manual", "agent", "order"]
    title: str
    summary: str


class EmailCheckRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    mailbox: str = "INBOX"
    recent: str | None = None
    unseen: bool = True


class EmailFetchRequest(BaseModel):
    uid: str = Field(min_length=1)
    mailbox: str = "INBOX"


class EmailSearchRequest(BaseModel):
    mailbox: str = "INBOX"
    limit: int = Field(default=20, ge=1, le=200)
    unseen: bool = False
    seen: bool = False
    from_email: str | None = None
    subject: str | None = None
    recent: str | None = None
    since: str | None = None
    before: str | None = None


class EmailSendRequest(BaseModel):
    to: str = Field(min_length=3)
    subject: str = Field(min_length=1)
    body: str | None = None
    html: bool = False
    cc: str | None = None
    bcc: str | None = None
    attach: str | None = None
    from_addr: str | None = None


class OrderRecord(BaseModel):
    id: str
    customer_id: str
    product_name: str
    quantity: int
    unit_price: float | None = None
    currency: str = "USD"
    total_amount: float | None = None
    status: OrderStatus = "待确认"
    created_at: str
    updated_at: str


class EmailProcessRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    mailbox: str = "INBOX"


class EmailProcessReport(BaseModel):
    scanned: int
    processed: int
    skipped: int
    review_queued: int
    orders_created: int
    timeline_added: int
    details: list[dict[str, object]] = []


class ScheduledJob(BaseModel):
    id: str
    job_type: str
    enabled: bool
    interval_seconds: int
    max_retries: int
    retry_count: int
    next_run_at: str
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class ReplyDraftRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    mailbox: str = "INBOX"
    uid: str | None = None
    tone: str = "professional"
    language: str = "en"
    additional_instruction: str | None = None


class ReplyDraftResponse(BaseModel):
    draft_id: str | None = None
    subject: str
    body: str
    context_used: list[str]
    suggestions: list[str]


class ReplyDraftRecord(BaseModel):
    id: str
    customer_id: str
    mailbox: str
    recipient: str | None = None
    subject: str
    body: str
    status: Literal["draft", "pending_approval", "approved", "rejected", "sent"]
    created_at: str
    updated_at: str
    approved_by: str | None = None
    approved_at: str | None = None
    sent_at: str | None = None
    rejection_reason: str | None = None


class ReplyDraftUpdateRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


class ReplyDraftStatusRequest(BaseModel):
    actor: str = "operator"
    reason: str | None = None


class ReviewQueueItem(BaseModel):
    id: str
    mailbox: str
    uid: str
    customer_id: str
    intent: str
    classification_confidence: float
    extraction_confidence: float
    reasons: list[str]
    status: Literal["pending", "approved", "rejected"]
    created_at: str
    resolved_at: str | None = None
    resolver: str | None = None
    note: str | None = None


class ReviewQueueResolveRequest(BaseModel):
    action: Literal["approved", "rejected"]
    resolver: str = "operator"
    note: str | None = None


class ProductionScheduleItem(BaseModel):
    id: str
    order_id: str
    customer_id: str
    customer_name: str
    product_name: str
    quantity: int
    order_status: str
    line_name: str
    planned_start: str
    planned_end: str
    status: str
    progress: int


class ProductionPlanResponse(BaseModel):
    planned_count: int
    details: list[dict[str, object]] = []


class ProductionRescheduleRequest(BaseModel):
    line_name: str
    planned_start: str
    planned_end: str


class ProductionRescheduleResponse(BaseModel):
    updated: ProductionScheduleItem
    conflicts: list[dict[str, object]]
