# MSG91 email integration — design

**Status:** approved (ready for implementation plan)
**Date:** 2026-04-19
**Scope:** backend only (FastAPI)

## Goal

Replace the current SMTP-based OTP email sender with a general-purpose `EmailClient` that uses MSG91's transactional email API. All outbound email from the backend flows through this client. SMTP code and the `emails` Python dependency are removed.

## Non-goals

- Swapping email providers pluggably (no `Protocol`/interface layer) — YAGNI; if a second provider is ever needed, the class can be extracted then.
- Rate-limiting or retrying MSG91 calls — transient failures surface as 502 and the user retries.

## Revision 2026-04-19: pivoting from inline HTML to MSG91 templates

Verification during implementation found that MSG91's `/api/v5/email/send` endpoint is template-only — all public examples and MSG91's own help articles use `template_id` + variables; no reliable evidence exists for an inline-HTML field on v5. Sending inline HTML would rely on undocumented behaviour.

Pivot: a single OTP template is created once in the MSG91 dashboard with a `{{otp}}` variable slot. Its ID is configured via `MSG91_OTP_TEMPLATE_ID`. The `EmailClient` API shifts from `send(to, subject, html)` to `send(to_email, to_name, template_id, variables)`. The OTP HTML body that previously lived in `_send_otp_email` is deleted; rendering happens inside MSG91. Everything else in the design — DI wiring, `ExternalServiceError`, failure handling, 10s timeout, no dev bypass — is unchanged.

## Architecture

### New file: `app/core/email.py`

```python
class EmailClient:
    def __init__(self, http: httpx.AsyncClient): ...
    async def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html: str,
    ) -> None:
        """POST to MSG91 send-email; raise ExternalServiceError on non-2xx or timeout."""

async def get_email_client() -> EmailClient:
    """FastAPI dependency — returns a process-wide EmailClient."""
```

- A single `httpx.AsyncClient` is held at module scope in `app/core/email.py`, created on first access (or explicitly in `main.py` startup), and closed in `main.py` shutdown — mirroring how `app/core/redis.py` manages its pool.
- `get_email_client` returns the same `EmailClient` wrapper for every request (not a new instance); there's no per-request setup/teardown, so no generator is needed.

### Modified files

| File | Change |
|------|--------|
| `app/config.py` | Add `msg91_auth_key`, `msg91_email_domain` (default `"signalshift.in"`), `msg91_from_email` (default `"noreply@signalshift.in"`), `msg91_from_name` (default `"Signal Shift"`). Remove `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from_name`. |
| `app/core/exceptions.py` | Add `class ExternalServiceError(AppError)` mapping to `status_code=502`. Generic — reusable for future third-party integrations. |
| `app/auth/service.py` | `AuthService.__init__` takes an additional `email_client: EmailClient`. `_send_otp_email` rewritten to call `self.email_client.send(...)`. Remove `import emails` and `from emails.template import JinjaTemplate`. Remove the "SMTP not configured → log and return" fallback. Remove the `is_development → log OTP instead of send` branch — we always send in every environment. |
| `app/auth/router.py` | `_get_service` dependency signature adds `email_client: EmailClient = Depends(get_email_client)` and passes it into `AuthService(...)`. |
| `app/main.py` | If startup/shutdown is where the shared `httpx.AsyncClient` for the `EmailClient` lives, open it on startup and close it on shutdown (matching Redis lifecycle). |
| `pyproject.toml` | Remove `emails>=0.6`. |
| `.env.example` | Replace SMTP block with MSG91 block (see below). |
| `.env` (developer-local) | Same swap. `MSG91_AUTH_KEY` is already populated. |

### MSG91 request contract

- **Endpoint:** `POST https://control.msg91.com/api/v5/email/send`
- **Headers:** `Authkey: <msg91_auth_key>`, `Content-Type: application/json`
- **Body shape:**
  ```json
  {
    "to":       [{"name": "<recipient display name>", "email": "<recipient email>"}],
    "from":     {"name": "Signal Shift", "email": "noreply@signalshift.in"},
    "domain":   "signalshift.in",
    "mail_type_id": "1",
    "subject":  "<subject>",
    "body":     "<inline HTML>"
  }
  ```
- `mail_type_id: "1"` = transactional.
- Recipient display name: `user.full_name` if set, else the local-part of the email.
- **Verification at implementation time:** the exact field name for inline HTML (`body` vs `html` vs `message`) is not nailed in the public docs scraped during design. Implementer verifies against MSG91's docs (or with a scratch request) before finalizing `EmailClient.send`. Changing the field name is a local edit within `EmailClient.send`; no callers are affected.
- **Timeout:** 10 seconds, matching the Google token-verify call in `app/auth/service.py`.

### Failure handling

- Non-2xx response from MSG91 → `raise ExternalServiceError("Failed to send verification email", status_code=502)`.
- `httpx.TimeoutException` → same.
- The OTP is already in Redis when MSG91 is called. On MSG91 failure the Redis row is orphaned and expires in `OTP_EXPIRE_SECONDS` (5 min). No cleanup needed.
- The existing global exception handler in `app/main.py` converts `AppError` subclasses to JSON. A 502 reaches the client as `{"detail": "Failed to send verification email"}`.

### Boot behavior when `msg91_auth_key` is empty

- App still boots. Startup does not hard-fail.
- First `/auth/otp/send` call fails with `ExternalServiceError` 502.
- Rationale: a fresh checkout without an MSG91 key should still be able to run migrations, hit `/docs`, and run non-email-touching tests.

## Config changes

### `app/config.py`

Replace the SMTP block with:
```python
# ─── Email (MSG91) ───
msg91_auth_key: str = ""
msg91_email_domain: str = "signalshift.in"
msg91_from_email: str = "noreply@signalshift.in"
msg91_from_name: str = "Signal Shift"
```

### `.env.example`

Replace the SMTP block with:
```env
# ─── Email (MSG91) ───
MSG91_AUTH_KEY=
MSG91_EMAIL_DOMAIN=signalshift.in
MSG91_FROM_EMAIL=noreply@signalshift.in
MSG91_FROM_NAME=Signal Shift
```

## Testing

### New unit tests

**`tests/unit/core/test_email.py`:**
1. `EmailClient.send` builds the correct MSG91 request — URL, `Authkey` header, JSON body shape including `mail_type_id`, `domain`, `from`, `to`, `subject`, and the inline HTML body. Uses a stubbed `httpx.AsyncClient` that asserts on the outgoing request.
2. Non-2xx response → raises `ExternalServiceError` with `status_code=502`.
3. `httpx.TimeoutException` → raises `ExternalServiceError` with `status_code=502`.

**`tests/unit/auth/test_service.py` (amend):**
4. `AuthService.send_otp` — injects a fake `EmailClient` that records calls; asserts one call with the user's email, the expected subject, and an HTML body containing the OTP.
5. `AuthService.send_otp` — fake `EmailClient` raises `ExternalServiceError`; assert the exception propagates unchanged (HTTP layer is responsible for turning it into 502).
6. Remove / update any existing OTP tests that relied on the old SMTP-absence no-op.

### Out of scope

- Integration tests against live MSG91 (would consume quota and require a CI secret). One manual end-to-end check — verify an OTP email actually lands in a test inbox — before we consider the feature shipped.
- `EmailClient` lifecycle test (startup/shutdown). Exercised implicitly by any endpoint test.

## YAGNI / explicit non-features

- No `EmailClient` Protocol or multi-provider abstraction.
- No retry/backoff logic inside the client.
- No queued / async-worker delivery — the OTP send blocks the `/auth/otp/send` request. Acceptable because MSG91's endpoint is fast and failures are worth surfacing to the user.
- No email-template system in Python (Jinja etc.) — we keep the current inline f-string HTML for OTP; future emails can add templates if/when needed.

## Open questions

None remaining — the one implementation-time check (exact MSG91 inline-HTML field name) is documented above and does not block planning.
