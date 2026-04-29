from fastapi import APIRouter, HTTPException

from app.core.schemas import (
    EmailCheckRequest,
    EmailFetchRequest,
    EmailProcessReport,
    EmailProcessRequest,
    EmailSearchRequest,
    EmailSendRequest,
    ReplyDraftRecord,
    ReplyDraftRequest,
    ReplyDraftResponse,
    ReplyDraftStatusRequest,
    ReplyDraftUpdateRequest,
    ReviewQueueItem,
    ReviewQueueResolveRequest,
)
from app.services.email_orchestration_service import email_orchestration_service
from app.services.reply_generation_service import ReplyGenerationError, reply_generation_service
from app.services.email_tool_adapter import EmailToolError, email_tool_adapter
from app.services.persistence_service import persistence_service


router = APIRouter()


@router.get("/status")
def get_email_skill_status() -> dict[str, object]:
    return email_tool_adapter.status()


@router.post("/check")
async def check_email(payload: EmailCheckRequest) -> object:
    try:
        return await email_tool_adapter.check(
            limit=payload.limit,
            mailbox=payload.mailbox,
            recent=payload.recent,
            unseen=payload.unseen,
        )
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fetch")
async def fetch_email(payload: EmailFetchRequest) -> object:
    try:
        return await email_tool_adapter.fetch(uid=payload.uid, mailbox=payload.mailbox)
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search")
async def search_email(payload: EmailSearchRequest) -> object:
    try:
        return await email_tool_adapter.search(payload.model_dump())
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/send")
async def send_email(payload: EmailSendRequest) -> object:
    try:
        return await email_tool_adapter.send(payload.model_dump())
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/verify-smtp")
async def verify_smtp() -> object:
    try:
        return await email_tool_adapter.verify_smtp()
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/process-unread", response_model=EmailProcessReport)
async def process_unread_email(payload: EmailProcessRequest) -> EmailProcessReport:
    try:
        return await email_orchestration_service.process_unread(
            mailbox=payload.mailbox,
            limit=payload.limit,
        )
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reply-draft", response_model=ReplyDraftResponse)
async def generate_reply_draft(payload: ReplyDraftRequest) -> ReplyDraftResponse:
    try:
        return await reply_generation_service.generate_reply(
            customer_id=payload.customer_id,
            mailbox=payload.mailbox,
            uid=payload.uid,
            tone=payload.tone,
            language=payload.language,
            additional_instruction=payload.additional_instruction,
        )
    except ReplyGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/drafts", response_model=list[ReplyDraftRecord])
def list_reply_drafts(customer_id: str | None = None, status: str | None = None) -> list[ReplyDraftRecord]:
    rows = persistence_service.list_reply_drafts(customer_id=customer_id, status=status)
    return [ReplyDraftRecord(**row) for row in rows]


@router.patch("/drafts/{draft_id}", response_model=ReplyDraftRecord)
def update_reply_draft(draft_id: str, payload: ReplyDraftUpdateRequest) -> ReplyDraftRecord:
    updated = persistence_service.update_reply_draft_content(
        draft_id=draft_id,
        subject=payload.subject,
        body=payload.body,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ReplyDraftRecord(**updated)


@router.post("/drafts/{draft_id}/submit", response_model=ReplyDraftRecord)
def submit_reply_draft_for_approval(draft_id: str, payload: ReplyDraftStatusRequest) -> ReplyDraftRecord:
    draft = persistence_service.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] in {"approved", "sent"}:
        raise HTTPException(status_code=400, detail="Draft is already approved or sent")

    updated = persistence_service.set_reply_draft_status(
        draft_id=draft_id,
        status="pending_approval",
        actor=payload.actor,
        reason=payload.reason,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ReplyDraftRecord(**updated)


@router.post("/drafts/{draft_id}/approve", response_model=ReplyDraftRecord)
def approve_reply_draft(draft_id: str, payload: ReplyDraftStatusRequest) -> ReplyDraftRecord:
    draft = persistence_service.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] not in {"pending_approval", "draft", "rejected"}:
        raise HTTPException(status_code=400, detail="Draft cannot be approved in current status")

    updated = persistence_service.set_reply_draft_status(
        draft_id=draft_id,
        status="approved",
        actor=payload.actor,
        reason=payload.reason,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ReplyDraftRecord(**updated)


@router.post("/drafts/{draft_id}/reject", response_model=ReplyDraftRecord)
def reject_reply_draft(draft_id: str, payload: ReplyDraftStatusRequest) -> ReplyDraftRecord:
    draft = persistence_service.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] == "sent":
        raise HTTPException(status_code=400, detail="Sent draft cannot be rejected")

    updated = persistence_service.set_reply_draft_status(
        draft_id=draft_id,
        status="rejected",
        actor=payload.actor,
        reason=payload.reason,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ReplyDraftRecord(**updated)


@router.post("/drafts/{draft_id}/send", response_model=ReplyDraftRecord)
async def send_approved_reply_draft(draft_id: str) -> ReplyDraftRecord:
    draft = persistence_service.get_reply_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "approved":
        raise HTTPException(status_code=400, detail="Draft must be approved before sending")
    if not draft.get("recipient"):
        raise HTTPException(status_code=400, detail="Draft recipient is missing")

    try:
        await email_tool_adapter.send(
            {
                "to": draft["recipient"],
                "subject": draft["subject"],
                "body": draft["body"],
                "html": False,
            }
        )
    except EmailToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = persistence_service.set_reply_draft_status(
        draft_id=draft_id,
        status="sent",
        actor="system",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ReplyDraftRecord(**updated)


@router.get("/review-queue", response_model=list[ReviewQueueItem])
def list_review_queue(status: str | None = "pending") -> list[ReviewQueueItem]:
    rows = persistence_service.list_review_queue(status=status)
    return [ReviewQueueItem(**row) for row in rows]


@router.post("/review-queue/{item_id}/resolve", response_model=ReviewQueueItem)
def resolve_review_queue(item_id: str, payload: ReviewQueueResolveRequest) -> ReviewQueueItem:
    updated = persistence_service.resolve_review_queue_item(
        item_id=item_id,
        action=payload.action,
        resolver=payload.resolver,
        note=payload.note,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return ReviewQueueItem(**updated)
