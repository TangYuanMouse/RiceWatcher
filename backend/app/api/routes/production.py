from fastapi import APIRouter, HTTPException

from app.core.schemas import (
    DelayRiskReport,
    FactoryRecord,
    FulfillmentMilestoneItem,
    FulfillmentMilestoneUpdateRequest,
    FulfillmentTaskAssignFactoryRequest,
    FulfillmentTaskItem,
    ProductionPlanResponse,
    ProductionRescheduleRequest,
    ProductionRescheduleResponse,
    ProductionScheduleItem,
    SampleOrderConversionResponse,
    SampleOrderSuggestionResponse,
    SampleRequestCreateRequest,
    SampleRequestItem,
    SampleRequestItemUpdateRequest,
    SampleRequestRecord,
    SampleRequestUpdateRequest,
)
from app.services.delay_risk_service import delay_risk_service
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


@router.get("/factories", response_model=list[FactoryRecord])
def list_factories() -> list[FactoryRecord]:
    rows = persistence_service.list_factories()
    return [FactoryRecord(**row) for row in rows]


@router.get("/tasks", response_model=list[FulfillmentTaskItem])
def list_fulfillment_tasks(
    status: str | None = None,
    search: str | None = None,
) -> list[FulfillmentTaskItem]:
    rows = persistence_service.list_fulfillment_tasks(status=status, search=search)
    return [FulfillmentTaskItem(**row) for row in rows]


@router.get("/tasks/{task_id}/milestones", response_model=list[FulfillmentMilestoneItem])
def list_task_milestones(task_id: str) -> list[FulfillmentMilestoneItem]:
    rows = persistence_service.list_fulfillment_milestones(task_id)
    return [FulfillmentMilestoneItem(**row) for row in rows]


@router.patch("/tasks/{task_id}/assign-factory", response_model=FulfillmentTaskItem)
def assign_factory(task_id: str, payload: FulfillmentTaskAssignFactoryRequest) -> FulfillmentTaskItem:
    updated = persistence_service.assign_factory_to_fulfillment_task(
        task_id=task_id,
        factory_id=payload.factory_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Fulfillment task not found")
    return FulfillmentTaskItem(**updated)


@router.patch("/milestones/{milestone_id}", response_model=FulfillmentMilestoneItem)
def update_milestone(
    milestone_id: str,
    payload: FulfillmentMilestoneUpdateRequest,
) -> FulfillmentMilestoneItem:
    updated = persistence_service.update_fulfillment_milestone(
        milestone_id=milestone_id,
        status=payload.status,
        planned_date=payload.planned_date,
        actual_date=payload.actual_date,
        responsible_party=payload.responsible_party,
        note=payload.note,
        proof_url=payload.proof_url,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return FulfillmentMilestoneItem(**updated)


@router.post("/delay-risks/scan", response_model=DelayRiskReport)
def scan_delay_risks(auto_mark: bool = True) -> DelayRiskReport:
    return delay_risk_service.scan_and_mark(auto_mark=auto_mark)


@router.get("/samples", response_model=list[SampleRequestRecord])
def list_sample_requests(
    status: str | None = None,
    search: str | None = None,
) -> list[SampleRequestRecord]:
    rows = persistence_service.list_sample_requests(status=status, search=search)
    return [SampleRequestRecord(**row) for row in rows]


@router.post("/samples", response_model=SampleRequestRecord)
def create_sample_request(payload: SampleRequestCreateRequest) -> SampleRequestRecord:
    created = persistence_service.create_sample_request(
        customer_id=payload.customer_id,
        factory_id=payload.factory_id,
        categories=[x.model_dump() for x in payload.categories],
        note=payload.note,
    )
    return SampleRequestRecord(**created)


@router.get("/samples/{sample_id}/items", response_model=list[SampleRequestItem])
def list_sample_request_items(sample_id: str) -> list[SampleRequestItem]:
    rows = persistence_service.list_sample_request_items(sample_id)
    return [SampleRequestItem(**row) for row in rows]


@router.patch("/samples/{sample_id}", response_model=SampleRequestRecord)
def update_sample_request(
    sample_id: str,
    payload: SampleRequestUpdateRequest,
) -> SampleRequestRecord:
    updated = persistence_service.update_sample_request(
        sample_id=sample_id,
        status=payload.status,
        feedback=payload.feedback,
        decision=payload.decision,
        note=payload.note,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    return SampleRequestRecord(**updated)


@router.patch("/sample-items/{item_id}", response_model=SampleRequestItem)
def update_sample_item(item_id: str, payload: SampleRequestItemUpdateRequest) -> SampleRequestItem:
    updated = persistence_service.update_sample_request_item(
        item_id=item_id,
        status=payload.status,
        tracking_no=payload.tracking_no,
        note=payload.note,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Sample item not found")
    return SampleRequestItem(**updated)


@router.get("/samples/{sample_id}/order-suggestions", response_model=SampleOrderSuggestionResponse)
def get_sample_order_suggestions(sample_id: str) -> SampleOrderSuggestionResponse:
    data = persistence_service.generate_sample_order_suggestions(sample_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    return SampleOrderSuggestionResponse(**data)


@router.post("/samples/{sample_id}/convert-to-orders", response_model=SampleOrderConversionResponse)
def convert_sample_to_orders(sample_id: str) -> SampleOrderConversionResponse:
    data = persistence_service.convert_sample_to_order_drafts(sample_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    return SampleOrderConversionResponse(**data)


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
