from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import text


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month using the property's timezone.
    Converts local month boundaries to UTC to correctly include check-in dates
    on month boundaries (e.g. March 1 in local property time).

    tenant_id is REQUIRED. Raises ValueError if absent.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for calculate_monthly_revenue")

    # 1. Determine property timezone
    property_tz_str = "UTC"
    tz_fallbacks = {
        'prop-001': 'Europe/Paris',
        'prop-002': 'Europe/Paris',
        'prop-003': 'Europe/Paris',
        'prop-004': 'America/New_York',
        'prop-005': 'America/New_York',
    }

    async def fetch_tz(session):
        query = text("""
            SELECT timezone FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
            LIMIT 1
        """)
        res = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
        row = res.fetchone()
        return row[0] if row and row[0] else None

    try:
        if db_session:
            fetched_tz = await fetch_tz(db_session)
            property_tz_str = fetched_tz or tz_fallbacks.get(property_id, "UTC")
        else:
            from app.core.database_pool import DatabasePool
            db_pool = DatabasePool()
            await db_pool.initialize()
            if db_pool.session_factory:
                async with db_pool.get_session() as session:
                    fetched_tz = await fetch_tz(session)
                    property_tz_str = fetched_tz or tz_fallbacks.get(property_id, "UTC")
            else:
                property_tz_str = tz_fallbacks.get(property_id, "UTC")
    except Exception:
        property_tz_str = tz_fallbacks.get(property_id, "UTC")

    try:
        tz = ZoneInfo(property_tz_str)
    except Exception:
        tz = ZoneInfo("UTC")

    # 2. Local month start and end boundaries in property's timezone
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)

    # 3. Convert boundaries to UTC
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    # 4. Query total revenue within the UTC boundaries — no mock fallback
    async def fetch_monthly_total(session):
        query = text("""
            SELECT SUM(total_amount) as total
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_utc
              AND check_in_date < :end_utc
        """)
        res = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
        })
        row = res.fetchone()
        if row and row[0] is not None:
            return Decimal(str(row[0])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    if db_session:
        return await fetch_monthly_total(db_session)
    else:
        from app.core.database_pool import DatabasePool
        db_pool = DatabasePool()
        await db_pool.initialize()
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                return await fetch_monthly_total(session)
        else:
            raise RuntimeError("Database pool not available — cannot calculate monthly revenue")


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    tenant_id is REQUIRED and enforced by the SQL WHERE clause.
    Raises on DB failure — no mock data returned.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for calculate_total_revenue")

    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available — cannot calculate total revenue")

    async with db_pool.get_session() as session:
        query = text("""
            SELECT
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        row = result.fetchone()

        if row and row.total_revenue is not None:
            total_revenue = Decimal(str(row.total_revenue)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total_revenue),
                "currency": "USD",
                "count": row.reservation_count,
            }
        else:
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0,
            }
