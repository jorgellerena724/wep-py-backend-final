from datetime import date, datetime, timedelta
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
import logging
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)
from sqlalchemy.orm.attributes import flag_modified
from app.api.endpoints.metrics_config import get_active_events, get_config_record
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_daily_metrics_model import DailyMetrics

router = APIRouter()

@router.patch("/update-metric/{event_name}/")
def increment_metric(
    event_name: str,
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    active = get_active_events(db)
    if event_name not in active:
        raise HTTPException(status_code=400, detail=f"Evento '{event_name}' no está configurado")

    today = date.today()
    record = db.get(DailyMetrics, today)
    if not record:
        record = DailyMetrics(daily_date=today, counters={})
        db.add(record)
        db.flush()

    new_value = record.counters.get(event_name, 0) + 1
    record.counters[event_name] = new_value
    flag_modified(record, "counters")
    db.commit()

    return {"date": today, "event": event_name, "value": new_value}

@router.get("/today/")
def get_today_metrics(
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    logger.info("🚀 /metrics/today/: Entrando al endpoint")
    today  = date.today()
    record = db.get(DailyMetrics, today)
    events = get_active_events(db)
    return {
        "date": today,
        "counters": {e: record.counters.get(e, 0) for e in events} if record else {e: 0 for e in events}
    }

@router.get("/range/")
def get_metrics_range(
    start_date: date = Query(...),
    end_date:   date = Query(...),
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date debe ser anterior a end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="El rango máximo es 90 días")

    events  = get_active_events(db)
    records = db.exec(
        select(DailyMetrics)
        .where(DailyMetrics.daily_date >= start_date)
        .where(DailyMetrics.daily_date <= end_date)
        .order_by(DailyMetrics.daily_date)
    ).all()
    records_by_date = {r.daily_date: r for r in records}

    result  = []
    current = start_date
    while current <= end_date:
        record = records_by_date.get(current)
        result.append({
            "date": current,
            "counters": {e: record.counters.get(e, 0) for e in events} if record else {e: 0 for e in events}
        })
        current += timedelta(days=1)
    return result


@router.get("/summary/")
def get_metrics_summary(
    start_date: date = Query(...),
    end_date:   date = Query(...),
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="El rango máximo es 90 días")

    events  = get_active_events(db)
    records = db.exec(
        select(DailyMetrics)
        .where(DailyMetrics.daily_date >= start_date)
        .where(DailyMetrics.daily_date <= end_date)
    ).all()

    totals = {e: 0 for e in events}
    for record in records:
        for e in events:
            totals[e] += record.counters.get(e, 0)

    return {"start_date": start_date, "end_date": end_date, "days_with_data": len(records), "totals": totals}

@router.get("/server-time/")
def get_server_time(current_user = Depends(verify_token)):
    now = datetime.now()
    return {
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "America/Bogota"  # o el que uses en tu config
    }