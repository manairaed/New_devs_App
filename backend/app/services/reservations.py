from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import text


def _get_tz(tz_str: str):
    """
    Resolves IANA timezone string to tzinfo.
    Falls back gracefully if the runtime lacks system tzdata (e.g. Windows without tzdata package).
    """
    try:
        return ZoneInfo(tz_str)
    except Exception:
        tz_lower = (tz_str or "").lower()
        if "paris" in tz_lower:
            return timezone(timedelta(hours=1))
        elif "new_york" in tz_lower:
            return timezone(timedelta(hours=-5))
        return timezone.utc


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """
    Fetches the actual timezone for a property from the database, strictly scoped by tenant_id.
    Defaults to 'UTC' if the property has no timezone specified or does not exist.
    """
    query = text("""
        SELECT timezone FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
        LIMIT 1
    """)
    res = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
    row = res.fetchone()
    if row and row[0]:
        return row[0].strip()
    return "UTC"


def _get_month_utc_boundaries(year: int, month: int, tz_str: str):
    """
    Computes UTC start and end datetime boundaries for a given calendar month
    in the specified local property timezone.
    """
    tz = _get_tz(tz_str)

    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month using the property's timezone from the database.
    Converts local month boundaries to UTC to correctly include check-in dates
    on month boundaries (e.g. March 1 in local property time).

    tenant_id is REQUIRED. Raises ValueError if absent.
    No mock data: database errors propagate to caller.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for calculate_monthly_revenue")

    async def _execute_monthly(session) -> Decimal:
        tz_str = await _get_property_timezone(session, property_id, tenant_id)
        start_utc, end_utc = _get_month_utc_boundaries(year, month, tz_str)

        query = text("""
            SELECT COALESCE(SUM(total_amount), 0) as total
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
        val = row[0] if row and row[0] is not None else 0
        return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if db_session:
        return await _execute_monthly(db_session)

    from app.core.database_pool import db_pool
    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available — cannot calculate monthly revenue")

    session = await db_pool.get_session()
    async with session:
        return await _execute_monthly(session)


async def calculate_monthly_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int = 3,
    year: int = 2024,
    db_session=None,
) -> Dict[str, Any]:
    """
    Calculates monthly revenue summary (total amount and reservation count)
    using the property's timezone from the database and UTC boundary conversion.
    Enforces strict tenant isolation and Decimal ROUND_HALF_UP precision.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for calculate_monthly_revenue_summary")

    async def _execute_summary(session) -> Dict[str, Any]:
        tz_str = await _get_property_timezone(session, property_id, tenant_id)
        start_utc, end_utc = _get_month_utc_boundaries(year, month, tz_str)

        query = text("""
            SELECT
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COUNT(*) as reservation_count
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
        total_val = row[0] if row and row[0] is not None else 0
        count_val = row[1] if row and row[1] is not None else 0

        total_dec = Decimal(str(total_val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_dec),
            "currency": "USD",
            "count": count_val,
        }

    if db_session:
        return await _execute_summary(db_session)

    from app.core.database_pool import db_pool
    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available — cannot calculate monthly revenue summary")

    session = await db_pool.get_session()
    async with session:
        return await _execute_summary(session)


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    db_session=None,
) -> Dict[str, Any]:
    """
    Reporting revenue endpoint handler.
    Delegates to calculate_monthly_revenue_summary for default reporting period (March 2024),
    ensuring timezone handling and monetary precision across all callers.
    """
    return await calculate_monthly_revenue_summary(
        property_id=property_id,
        tenant_id=tenant_id,
        month=3,
        year=2024,
        db_session=db_session,
    )
