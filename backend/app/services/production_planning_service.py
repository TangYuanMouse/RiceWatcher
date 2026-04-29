from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.schemas import ProductionPlanResponse
from app.services.persistence_service import persistence_service


class ProductionPlanningService:
    @staticmethod
    def _days_for_quantity(quantity: int) -> int:
        return max(2, min(15, int(quantity / 800) + 2))

    @staticmethod
    def _progress_from_status(status: str) -> int:
        mapping = {
            "待确认": 5,
            "待付款": 15,
            "生产中": 55,
            "待发货": 85,
            "已发货": 100,
            "已完成": 100,
        }
        return mapping.get(status, 0)

    @staticmethod
    def _task_status_from_order_status(status: str) -> str:
        if status in {"待确认", "待付款"}:
            return "planned"
        if status in {"生产中", "待发货"}:
            return "in_progress"
        if status in {"已发货", "已完成"}:
            return "done"
        return "planned"

    @staticmethod
    def _milestone_status_from_order_status(order_status: str, sequence: int) -> str:
        if order_status in {"待确认", "待付款"}:
            return "planned"
        if order_status == "生产中":
            return "in_progress" if sequence == 1 else "planned"
        if order_status == "待发货":
            if sequence <= 2:
                return "done"
            if sequence == 3:
                return "in_progress"
            return "planned"
        if order_status == "已发货":
            return "done" if sequence <= 4 else "in_progress"
        if order_status == "已完成":
            return "done"
        return "planned"

    @staticmethod
    def _build_milestones(base_start: datetime, duration_days: int, order_status: str) -> list[dict[str, Any]]:
        plan_points = [
            ("production", 0, "factory"),
            ("inspection", max(1, duration_days - 1), "factory_qc"),
            ("customs_declaration", duration_days + 1, "trade_operator"),
            ("shipment", duration_days + 2, "forwarder"),
            ("loading", duration_days + 4, "port_operator"),
        ]

        milestones: list[dict[str, Any]] = []
        for idx, (name, plus_days, owner) in enumerate(plan_points, start=1):
            planned_date = (base_start + timedelta(days=plus_days)).replace(microsecond=0).isoformat()
            milestone_status = ProductionPlanningService._milestone_status_from_order_status(
                order_status,
                idx,
            )
            milestones.append(
                {
                    "milestone_name": name,
                    "sequence": idx,
                    "status": milestone_status,
                    "planned_date": planned_date,
                    "actual_date": planned_date if milestone_status == "done" else None,
                    "responsible_party": owner,
                }
            )
        return milestones

    async def plan_from_orders(self) -> ProductionPlanResponse:
        active_orders = persistence_service.list_orders()
        factories = persistence_service.list_factories()
        if not factories:
            return ProductionPlanResponse(planned_count=0, details=[])

        start_cursor = datetime.now(timezone.utc)

        planned = 0
        details: list[dict[str, Any]] = []

        for idx, order in enumerate(active_orders):
            if order["status"] in {"已完成"}:
                continue

            duration_days = self._days_for_quantity(int(order["quantity"]))
            assigned_factory = factories[idx % len(factories)]
            planned_start_dt = start_cursor + timedelta(days=idx)
            planned_end_dt = start_cursor + timedelta(days=idx + duration_days + 4)
            planned_start = planned_start_dt.replace(microsecond=0).isoformat()
            planned_end = planned_end_dt.replace(microsecond=0).isoformat()
            progress = self._progress_from_status(order["status"])
            task_status = self._task_status_from_order_status(order["status"])

            task_id = persistence_service.upsert_fulfillment_task(
                order_id=order["id"],
                customer_id=order["customer_id"],
                factory_id=assigned_factory["id"],
                status=task_status,
                planned_start=planned_start,
                planned_end=planned_end,
            )

            milestones = self._build_milestones(
                base_start=planned_start_dt,
                duration_days=duration_days,
                order_status=order["status"],
            )
            persistence_service.upsert_fulfillment_milestones(task_id=task_id, milestones=milestones)

            # Keep legacy schedule table in sync for compatibility with existing clients.
            persistence_service.upsert_production_schedule(
                order_id=order["id"],
                customer_id=order["customer_id"],
                line_name=assigned_factory["name"],
                planned_start=planned_start,
                planned_end=planned_end,
                status="active" if progress < 100 else "done",
                progress=progress,
            )

            planned += 1
            details.append(
                {
                    "task_id": task_id,
                    "order_id": order["id"],
                    "factory_name": assigned_factory["name"],
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    "progress": progress,
                    "milestones": len(milestones),
                }
            )

        return ProductionPlanResponse(planned_count=planned, details=details)


production_planning_service = ProductionPlanningService()
