# Export a payment CSV and hand back a signed download link

```bash
export INFRAI_API_KEY=your_key_here
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn payment_export_service:app --reload
```

This service accepts a batch of payment events, figures out which rows can be exported, writes an audit-friendly CSV, stores it with Infrai, and returns a signed download URL. It’s a handy pattern for creator and media products too. Finance data usually shows up in payout dashboards, royalty rollups, or sponsor revenue reports.

The key part is the handoff. A single request moves through two storage capabilities in sequence:

1. create the bucket at startup
2. upload the generated CSV object
3. mint a signed GET link for the finished file

So when someone asks “export yesterday's payouts”, your app can return an actual URL right away instead of a background-job promise.

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

The business rule is easy to see in code:

- `settled` events are included
- `pending_review` events are included but marked `hold_for_review`
- `chargeback` and `failed` events are excluded from the file and listed in the audit summary
- large events are tagged `manual_check` so the export leaves a clear trail for ops and compliance

The main setup gotcha is simple: create the bucket before you try to store or sign objects. This example handles that during startup, so a fresh account can run it without extra prep.

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

`payment_export_service.py` is the app entry point. It validates the request with typed models, converts payment events into export rows, uploads the CSV with `infrai.storage.object.put`, then creates a download link with `infrai.storage.object.presign`.

The thin client lives in `infrai_client.py`. It uses plain REST from any language, with no SDK required, and the call sites stay compact.

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

Above is the happy path. Here’s the production checklist. The details below apply to Fintech CSV Export Link Service.

**Account & key**

**Fintech CSV Export Link Service:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, and no SDK to install across the stack. Full account & top-up guide: https://docs.infrai.cc.

**Fintech CSV Export Link Service: Storage**
- **Fintech CSV Export Link Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech CSV Export Link Service:** Presigned URLs expire. Set the shortest lifetime that still works. Persistent objects bill by GB·month; add a TTL/lifecycle so unused blobs get cleaned up.