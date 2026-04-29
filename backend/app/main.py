from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.persistence_service import persistence_service
from app.services.scheduler_service import scheduler_service


app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
async def on_startup() -> None:
    persistence_service.init_db()
    persistence_service.seed_demo_data()
    await scheduler_service.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await scheduler_service.stop()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "api": settings.api_prefix,
    }
