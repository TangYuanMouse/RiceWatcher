from fastapi import APIRouter

from app.api.routes import (
	automation,
	customers,
	email,
	gateway,
	health,
	orders,
	production,
	timeline,
)


api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(gateway.router, prefix="/gateway", tags=["gateway"])
api_router.include_router(email.router, prefix="/email", tags=["email"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(production.router, prefix="/production", tags=["production"])
api_router.include_router(automation.router, prefix="/automation", tags=["automation"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(timeline.router, prefix="/timeline", tags=["timeline"])
