from fastapi import APIRouter, HTTPException

from app.core.schemas import ScheduledJob
from app.services.persistence_service import persistence_service
from app.services.scheduler_service import scheduler_service


router = APIRouter()


@router.get("/jobs", response_model=list[ScheduledJob])
def list_jobs() -> list[ScheduledJob]:
    rows = persistence_service.list_jobs()
    return [
        ScheduledJob(
            id=row["id"],
            job_type=row["job_type"],
            enabled=row["enabled"],
            interval_seconds=row["interval_seconds"],
            max_retries=row["max_retries"],
            retry_count=row["retry_count"],
            next_run_at=row["next_run_at"],
            last_run_at=row["last_run_at"],
            last_status=row["last_status"],
            last_error=row["last_error"],
        )
        for row in rows
    ]


@router.post("/jobs/{job_id}/run-now")
async def run_job_now(job_id: str) -> dict[str, str]:
    rows = persistence_service.list_jobs()
    if not any(row["id"] == job_id for row in rows):
        raise HTTPException(status_code=404, detail="Job not found")
    await scheduler_service.run_job_now(job_id)
    return {"status": "scheduled", "job_id": job_id}


@router.post("/jobs/{job_id}/enable")
def enable_job(job_id: str) -> dict[str, object]:
    rows = persistence_service.list_jobs()
    if not any(row["id"] == job_id for row in rows):
        raise HTTPException(status_code=404, detail="Job not found")
    persistence_service.set_job_enabled(job_id, True)
    return {"status": "enabled", "job_id": job_id}


@router.post("/jobs/{job_id}/disable")
def disable_job(job_id: str) -> dict[str, object]:
    rows = persistence_service.list_jobs()
    if not any(row["id"] == job_id for row in rows):
        raise HTTPException(status_code=404, detail="Job not found")
    persistence_service.set_job_enabled(job_id, False)
    return {"status": "disabled", "job_id": job_id}
