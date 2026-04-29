from fastapi import APIRouter, Query

from app.core.schemas import OrderRecord
from app.services.persistence_service import persistence_service


router = APIRouter()


@router.get("/", response_model=list[OrderRecord])
def list_orders(
    customer_id: str | None = Query(None),
    status: str | None = Query(None),
) -> list[OrderRecord]:
    rows = persistence_service.list_orders(customer_id=customer_id, status=status)
    return [OrderRecord(**row) for row in rows]
