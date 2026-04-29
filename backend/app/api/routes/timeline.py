from fastapi import APIRouter, Query

from app.core.schemas import TimelineEvent
from app.services.persistence_service import persistence_service


router = APIRouter()


@router.get("/events", response_model=list[TimelineEvent])
def list_timeline_events(customer_id: str | None = Query(None)) -> list[TimelineEvent]:
    rows = persistence_service.list_timeline_events(customer_id=customer_id)
    return [TimelineEvent(**row) for row in rows]
