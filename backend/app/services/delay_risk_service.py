from datetime import datetime, timezone

from app.core.schemas import DelayRiskItem, DelayRiskReport
from app.services.persistence_service import persistence_service


def _parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class DelayRiskService:
    def scan_and_mark(self, auto_mark: bool = True) -> DelayRiskReport:
        rows = persistence_service.list_fulfillment_milestones_with_context()
        now = datetime.now(timezone.utc)

        items: list[DelayRiskItem] = []
        auto_marked = 0
        for row in rows:
            status = str(row.get("status") or "planned")
            if status == "done":
                continue

            planned = _parse_iso(str(row["planned_date"]))
            overdue_days = (now - planned).days
            days_to_due = (planned - now).days

            risk_level: str | None = None
            if overdue_days >= 0:
                if overdue_days >= 3:
                    risk_level = "high"
                else:
                    risk_level = "medium"
            elif days_to_due <= 2:
                risk_level = "low"

            if risk_level is None:
                continue

            next_status = status
            if auto_mark and overdue_days >= 0 and status not in {"delayed", "blocked"}:
                updated = persistence_service.update_fulfillment_milestone(
                    milestone_id=str(row["milestone_id"]),
                    status="delayed",
                )
                if updated is not None:
                    next_status = "delayed"
                    auto_marked += 1

            reminder = (
                f"{row['customer_name']} / {row['factory_name']} milestone "
                f"'{row['milestone_name']}' needs attention."
            )
            items.append(
                DelayRiskItem(
                    milestone_id=str(row["milestone_id"]),
                    task_id=str(row["task_id"]),
                    order_id=str(row["order_id"]),
                    customer_name=str(row["customer_name"]),
                    factory_name=str(row["factory_name"]),
                    milestone_name=str(row["milestone_name"]),
                    planned_date=str(row["planned_date"]),
                    status=next_status,  # type: ignore[arg-type]
                    overdue_days=max(0, overdue_days),
                    risk_level=risk_level,  # type: ignore[arg-type]
                    reminder=reminder,
                )
            )

        return DelayRiskReport(
            scanned=len(rows),
            at_risk=len(items),
            auto_marked=auto_marked,
            items=items,
        )


delay_risk_service = DelayRiskService()
