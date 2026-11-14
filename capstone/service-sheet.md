# Service sheet (one page per squad, sent to Avashya at least 3 days before the workshop)

**Synthetic data only.** Do not include production data, credentials, customer information or proprietary source code. Describe your service; we model mock data on it.

| Field | Your answer | Example |
|---|---|---|
| Squad name | | `payouts` |
| Service and one-line purpose | | `kyc-svc`: verifies PAN and Aadhaar through a third-party KYC provider |
| Stack | | Go, MongoDB `kyc_requests`, CloudWatch `/ecs/kyc-*` |
| Key dependencies | | KYC vendor API, notifications service |
| Top 3 failure modes | 1. <br>2. <br>3. | Vendor timeouts; OTP delivery failures; stuck `PENDING` requests |
| One past incident, sanitized | Symptom, timeline, root cause, fix | Retry-policy change raised vendor timeouts after a deploy |
| Forbidden zones (things the agent must never touch) | | PII retention logic; `kyc_documents` writes |
| SLOs | | p95 under 3 s; success rate over 98 percent |
| One field the agent should never reveal | | PAN number |

No sheet? Pick a **ready profile**: `kyc-svc`, `mandates-svc`, `ledger-recon`, `notifications-svc`, `nav-ingest` (see `capstone/profiles/`).
