from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from typing import List, Tuple

from pydantic import BaseModel, Field


MANUAL_CHECK_THRESHOLD_CENTS = 250000


class PaymentEvent(BaseModel):
    event_id: str
    creator_id: str
    amount_cents: int = Field(ge=0)
    currency: str
    status: str
    occurred_at: str
    description: str


class PaymentExportRequest(BaseModel):
    account_id: str
    requested_by: str
    notification_channel: str
    events: List[PaymentEvent]


class AuditSummary(BaseModel):
    notification_channel: str
    requested_by: str
    blocked_event_ids: List[str]


class PaymentExportResponse(BaseModel):
    export_id: str
    object_key: str
    download_url: str
    included_event_count: int
    blocked_event_count: int
    audit_summary: AuditSummary


@dataclass
class ExportBuildResult:
    export_id: str
    object_key: str
    csv_text: str
    included_event_count: int
    blocked_event_count: int
    blocked_event_ids: List[str]


ALLOWED_STATUSES = {"settled", "pending_review", "failed", "chargeback"}


def decide_export_action(event: PaymentEvent) -> Tuple[str, str]:
    status = event.status
    if status not in ALLOWED_STATUSES:
        return "exclude", "unknown_status"
    if status == "settled":
        base_action = "include"
    elif status == "pending_review":
        base_action = "hold_for_review"
    else:
        return "exclude", status

    if event.amount_cents >= MANUAL_CHECK_THRESHOLD_CENTS:
        return base_action, "manual_check"
    return base_action, "clear"


def build_payment_export(req: PaymentExportRequest) -> ExportBuildResult:
    export_id = f"exp_{uuid.uuid4().hex[:12]}"
    object_key = f"exports/{req.account_id}/{export_id}.csv"
    blocked_event_ids: List[str] = []

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "event_id",
            "creator_id",
            "amount_cents",
            "currency",
            "status",
            "occurred_at",
            "description",
            "export_action",
            "risk_flag",
            "requested_by",
            "notification_channel",
        ]
    )

    included_count = 0
    for event in req.events:
        action, risk_flag = decide_export_action(event)
        if action == "exclude":
            blocked_event_ids.append(event.event_id)
            continue
        included_count += 1
        writer.writerow(
            [
                event.event_id,
                event.creator_id,
                event.amount_cents,
                event.currency,
                event.status,
                event.occurred_at,
                event.description,
                action,
                risk_flag,
                req.requested_by,
                req.notification_channel,
            ]
        )

    return ExportBuildResult(
        export_id=export_id,
        object_key=object_key,
        csv_text=buffer.getvalue(),
        included_event_count=included_count,
        blocked_event_count=len(blocked_event_ids),
        blocked_event_ids=blocked_event_ids,
    )
