from payment_export_domain import PaymentExportRequest, build_payment_export


def test_payment_export_filters_and_marks_risk() -> None:
    req = PaymentExportRequest.model_validate(
        {
            "account_id": "acct_media_7",
            "requested_by": "ops@studio.test",
            "notification_channel": "email:finance@studio.test",
            "events": [
                {
                    "event_id": "pay_ok",
                    "creator_id": "creator_a",
                    "amount_cents": 15000,
                    "currency": "USD",
                    "status": "settled",
                    "occurred_at": "2026-05-01T10:00:00Z",
                    "description": "Sponsor payout",
                },
                {
                    "event_id": "pay_hold",
                    "creator_id": "creator_b",
                    "amount_cents": 500000,
                    "currency": "USD",
                    "status": "pending_review",
                    "occurred_at": "2026-05-01T10:30:00Z",
                    "description": "Large licensing transfer",
                },
                {
                    "event_id": "pay_blocked",
                    "creator_id": "creator_c",
                    "amount_cents": 2500,
                    "currency": "USD",
                    "status": "chargeback",
                    "occurred_at": "2026-05-01T11:00:00Z",
                    "description": "Reversed fan payment",
                },
            ],
        }
    )

    result = build_payment_export(req)

    assert result.included_event_count == 2
    assert result.blocked_event_count == 1
    assert result.blocked_event_ids == ["pay_blocked"]
    assert "pay_ok" in result.csv_text
    assert "include,clear" in result.csv_text
    assert "pay_hold" in result.csv_text
    assert "hold_for_review,manual_check" in result.csv_text
    assert "pay_blocked" not in result.csv_text
