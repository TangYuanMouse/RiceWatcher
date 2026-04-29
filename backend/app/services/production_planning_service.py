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

    async def plan_from_orders(self) -> ProductionPlanResponse:
        active_orders = persistence_service.list_orders()
        start_cursor = datetime.now(timezone.utc)
        lines = ["Line-A", "Line-B", "Line-C"]

        planned = 0
        details: list[dict[str, Any]] = []

        for idx, order in enumerate(active_orders):
            if order["status"] in {"已完成"}:
                continue

            duration_days = self._days_for_quantity(int(order["quantity"]))
            line_name = lines[idx % len(lines)]
            planned_start = (start_cursor + timedelta(days=idx)).replace(microsecond=0).isoformat()
            planned_end = (start_cursor + timedelta(days=idx + duration_days)).replace(microsecond=0).isoformat()
            progress = self._progress_from_status(order["status"])

            persistence_service.upsert_production_schedule(
                order_id=order["id"],
                customer_id=order["customer_id"],
                line_name=line_name,
                planned_start=planned_start,
                planned_end=planned_end,
                status="active" if progress < 100 else "done",
                progress=progress,
            )

            planned += 1
            details.append(
                {
                    "order_id": order["id"],
                    "line_name": line_name,
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    "progress": progress,
                }
            )

        return ProductionPlanResponse(planned_count=planned, details=details)


production_planning_service = ProductionPlanningService()
