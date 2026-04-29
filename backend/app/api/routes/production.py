from fastapi import APIRouter, HTTPException

from app.core.schemas import (
    ProductionPlanResponse,
    ProductionRescheduleRequest,
    ProductionRescheduleResponse,
    ProductionScheduleItem,
)
from app.services.persistence_service import persistence_service
from app.services.production_planning_service import production_planning_service


router = APIRouter()


@router.get("/schedule", response_model=list[ProductionScheduleItem])
def get_production_schedule() -> list[ProductionScheduleItem]:
    rows = persistence_service.list_production_schedule()
    return [ProductionScheduleItem(**row) for row in rows]


@router.post("/plan", response_model=ProductionPlanResponse)
async def plan_production_schedule() -> ProductionPlanResponse:
    return await production_planning_service.plan_from_orders()


@router.patch("/schedule/{schedule_id}/reschedule", response_model=ProductionRescheduleResponse)
def reschedule_production_item(
    schedule_id: str,
    payload: ProductionRescheduleRequest,
) -> ProductionRescheduleResponse:
    updated = persistence_service.reschedule_production_item(
        schedule_id=schedule_id,
        line_name=payload.line_name,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    conflicts = persistence_service.detect_schedule_conflicts(
        schedule_id=schedule_id,
        line_name=payload.line_name,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
    )
    return ProductionRescheduleResponse(
        updated=ProductionScheduleItem(**updated),
        conflicts=conflicts,
    )
