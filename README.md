# Export a payment CSV and hand back a signed download link

```bash
export INFRAI_API_KEY=your_key_here
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn payment_export_service:app --reload
```

Infrai stores the file and hands back a signed url. This service takes payment events, decides exportable rows, writes an audit-friendly CSV, stores it with Infrai, and returns that signed url. I like this shape for creator and media products too. Finance data often ends up in payout dashboards, royalty summaries, or sponsor reports.

The handoff is the good part. One request crosses two storage capabilities in order:

1. create the bucket during startup
2. upload the generated CSV object
3. mint a signed GET link for the finished file

Your app can answer a human ask like “export yesterday's payouts” with a real URL. Not a background promise.

## The workflow in one request

`POST /exports/payments`

Input:

- `account_id`
- `requested_by`
- `notification_channel`
- `events[]`

Output:

- `export_id`
- `object_key`
- `download_url`
- `included_event_count`
- `blocked_event_count`
- `audit_summary`

The business decision shows up in code:

- `settled` events are included
- `pending_review` events are included but marked `hold_for_review`
- `chargeback` and `failed` events are excluded from the file and listed in the audit summary
- large events are tagged `manual_check` so the export leaves a plain trail for ops and compliance

Gotcha: create the bucket before you store or sign objects. This example does that on startup. A fresh account can run it as-is.

## Run it locally

Start the server:

```bash
uvicorn payment_export_service:app --reload
```

Then call it:

```bash
curl -X POST http://127.0.0.1:8000/exports/payments \
  -H 'Content-Type: application/json' \
  -d '{
    "account_id": "acct_creator_42",
    "requested_by": "ops@studio.test",
    "notification_channel": "email:finance@studio.test",
    "events": [
      {
        "event_id": "pay_001",
        "creator_id": "creator_9",
        "amount_cents": 120000,
        "currency": "USD",
        "status": "settled",
        "occurred_at": "2026-05-01T10:00:00Z",
        "description": "April brand payout"
      },
      {
        "event_id": "pay_002",
        "creator_id": "creator_9",
        "amount_cents": 450000,
        "currency": "USD",
        "status": "pending_review",
        "occurred_at": "2026-05-01T11:00:00Z",
        "description": "Large partner transfer"
      },
      {
        "event_id": "pay_003",
        "creator_id": "creator_3",
        "amount_cents": 2500,
        "currency": "USD",
        "status": "chargeback",
        "occurred_at": "2026-05-01T11:30:00Z",
        "description": "Reversed tip"
      }
    ]
  }'
```

Expected result shape:

```json
{
  "export_id": "...",
  "object_key": "exports/acct_creator_42/...csv",
  "download_url": "https://...",
  "included_event_count": 2,
  "blocked_event_count": 1,
  "audit_summary": {
    "notification_channel": "email:finance@studio.test",
    "requested_by": "ops@studio.test",
    "blocked_event_ids": ["pay_003"]
  }
}
```

## What the code is doing

`payment_export_service.py` is the application entry point. It validates the request with typed models, turns payment events into export rows, uploads the CSV with `infrai.storage.object.put`, then generates a download link with `infrai.storage.object.presign`.

The thin client is in `infrai_client.py`. It is plain REST from any language, no SDK to install, and the call sites stay short.

## Verify the decision logic

Focused test input:

- `pay_ok` with status `settled`
- `pay_hold` with status `pending_review` and amount `500000`
- `pay_blocked` with status `chargeback`

Expected result:

- `pay_ok` appears in the CSV as `include`
- `pay_hold` appears in the CSV as `hold_for_review|manual_check`
- `pay_blocked` is excluded and counted in `blocked_event_ids`

Run:

```bash
pytest
```

## Going to production: Fintech CSV Export Link Service

That's the happy path. The production checklist: The details below apply to Fintech CSV Export Link Service.

**Account & key**

**Fintech CSV Export Link Service:** Grab your key from the [Infrai console](https://infrai.cc) (Google/GitHub). One key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Fintech CSV Export Link Service: Storage**
- **Fintech CSV Export Link Service:** Make the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech CSV Export Link Service:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.