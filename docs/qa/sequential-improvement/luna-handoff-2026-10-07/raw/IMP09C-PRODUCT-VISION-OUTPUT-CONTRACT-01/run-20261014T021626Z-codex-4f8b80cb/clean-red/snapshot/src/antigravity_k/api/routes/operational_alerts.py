from pathlib import Path
from typing import Annotated, ClassVar

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from antigravity_k.config import config
from antigravity_k.engine.operational_alert_store import (
    OperationalAlert,
    OperationalAlertStore,
    OperationalAlertStoreError,
)

router = APIRouter(prefix="/api/alerts")


class AlertAcknowledgementResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    alert_id: str
    acknowledged: bool


def _get_alert_store() -> OperationalAlertStore:
    path = Path(config.paths.project_root) / ".antigravity" / "operational_alerts.json"
    return OperationalAlertStore(path)


@router.get("", response_model=list[OperationalAlert])
async def list_operational_alerts(
    include_acknowledged: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OperationalAlert]:
    try:
        alerts = _get_alert_store().list_alerts(
            limit=limit,
            include_acknowledged=include_acknowledged,
        )
    except OperationalAlertStoreError as exc:
        raise HTTPException(status_code=503, detail="알림 저장소를 읽을 수 없습니다") from exc
    return list(alerts)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertAcknowledgementResponse,
)
async def acknowledge_operational_alert(alert_id: str) -> AlertAcknowledgementResponse:
    try:
        alert = _get_alert_store().acknowledge_one(alert_id)
    except OperationalAlertStoreError as exc:
        raise HTTPException(status_code=503, detail="알림 저장소를 갱신할 수 없습니다") from exc
    if alert is None:
        raise HTTPException(status_code=404, detail="대기 중인 알림을 찾을 수 없습니다")
    return AlertAcknowledgementResponse(alert_id=alert.alert_id, acknowledged=True)
