from fastapi import APIRouter, HTTPException

from app.core.schemas import Customer
from app.services.persistence_service import persistence_service


router = APIRouter()


@router.get("/", response_model=list[Customer])
def list_customers() -> list[Customer]:
    return [Customer(**item) for item in persistence_service.list_customers()]


@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: str) -> Customer:
    customer = persistence_service.get_customer(customer_id)
    if customer is not None:
        return Customer(**customer)
    raise HTTPException(status_code=404, detail="Customer not found")
