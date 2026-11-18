import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = 3,
    year: Optional[int] = 2024
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    Cache keys are isolated by both tenant_id and property_id to prevent cross-tenant data leaks.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required to fetch and cache revenue summary")

    target_month = month if month is not None else 3
    target_year = year if year is not None else 2024

    cache_key = f"revenue:{tenant_id}:{property_id}:{target_year}:{target_month}"
    
    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        # Fall back gracefully to direct calculation if Redis is unavailable
        pass
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue_summary
    
    # Calculate revenue using monthly reporting logic with timezone conversion
    result = await calculate_monthly_revenue_summary(
        property_id=property_id,
        tenant_id=tenant_id,
        month=target_month,
        year=target_year
    )
    
    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result
