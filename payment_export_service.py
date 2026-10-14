import base64

from fastapi import FastAPI

from infrai_client import infrai
from payment_export_domain import AuditSummary, PaymentExportRequest, PaymentExportResponse, build_payment_export


EXPORT_BUCKET = "payment-report-exports"

app = FastAPI(title="payment-export-service")


@app.on_event("startup")
def ensure_bucket() -> None:
    infrai.storage.bucket.create({"name": EXPORT_BUCKET})


@app.post("/exports/payments", response_model=PaymentExportResponse)
def create_payment_export(request: PaymentExportRequest) -> PaymentExportResponse:
    built = build_payment_export(request)
    encoded = base64.b64encode(built.csv_text.encode("utf-8")).decode("ascii")

    infrai.storage.object.put(
        EXPORT_BUCKET,
        built.object_key,
        {
            "data_base64": encoded,
            "content_type": "text/csv",
        },
    )

    presigned = infrai.storage.object.presign(
        EXPORT_BUCKET,
        built.object_key,
        {
            "op": "get",
            "expires_seconds": 900,
            "response_disposition": f'attachment; filename="{built.export_id}.csv"',
            "idempotency_key": built.export_id,
        },
    )

    return PaymentExportResponse(
        export_id=built.export_id,
        object_key=built.object_key,
        download_url=presigned["url"],
        included_event_count=built.included_event_count,
        blocked_event_count=built.blocked_event_count,
        audit_summary=AuditSummary(
            notification_channel=request.notification_channel,
            requested_by=request.requested_by,
            blocked_event_ids=built.blocked_event_ids,
        ),
    )
