from fastapi import APIRouter


router = APIRouter()


@router.get("/")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
