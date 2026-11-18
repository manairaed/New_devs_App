from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, description="Month (1-12)"),
    year: Optional[int] = Query(None, description="Year"),
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = None
    if isinstance(current_user, dict):
        tenant_id = current_user.get("tenant_id")
    else:
        tenant_id = getattr(current_user, "tenant_id", None)

    if not tenant_id or tenant_id == "default_tenant":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication context is missing a valid tenant_id"
        )
    
    revenue_data = await get_revenue_summary(
        property_id=property_id,
        tenant_id=tenant_id,
        month=month,
        year=year
    )
    
    # Ensure financial precision using Decimal ROUND_HALF_UP to two decimal places
    total_dec = Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_dec),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
