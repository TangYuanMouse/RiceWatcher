from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import llm_provider_config
from app.core.schemas import MessageIn, RunAccepted, RunEvent, RunInfo
from app.services.gateway_service import gateway_service


router = APIRouter()


@router.post("/messages", response_model=RunAccepted)
async def create_message(payload: MessageIn) -> RunAccepted:
    return await gateway_service.submit_message(payload)


@router.get("/runs/{run_id}", response_model=RunInfo)
def get_run(run_id: str) -> RunInfo:
    info = gateway_service.get_run_info(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return info


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
def get_run_events(run_id: str, start_index: int = Query(0, ge=0)) -> list[RunEvent]:
    return gateway_service.get_events(run_id=run_id, start_index=start_index)


@router.get("/runs/{run_id}/events/stream")
async def stream_run_events(run_id: str, start_index: int = Query(0, ge=0)):
    generator = gateway_service.stream_sse(run_id=run_id, start_index=start_index)
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/config/llm")
def get_llm_config_status() -> dict[str, object]:
    return {
        "provider": llm_provider_config.provider,
        "base_url": llm_provider_config.base_url,
        "model_name": llm_provider_config.model_name,
        "enabled": llm_provider_config.enabled,
        "configured": bool(
            llm_provider_config.base_url
            and llm_provider_config.api_key
            and llm_provider_config.model_name
        ),
    }


@router.get("/agents")
def list_gateway_agents() -> dict[str, object]:
    return {
        "supervisor": "gateway_supervisor_router",
        "agents": gateway_service.get_available_agents(),
    }
