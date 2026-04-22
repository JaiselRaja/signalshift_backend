"""
Inline HTML email templates — branded, email-safe (table-based layout,
inline CSS, dark header + light body).

Each function returns (subject, html, text) so callers can plug into
SendGridClient.send without further formatting.

Brand palette:
  ink       #121f00   (body copy on light)
  canvas    #ffffff   (card background)
  surface   #f6f8f4   (page background)
  border    #e4ead9
  muted     #707a6a
  primary   #004900   (deep green)
  accent    #b2f746   (lime)
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from app.config import settings


# ─── Helpers ─────────────────────────────────────────────

def _money(value) -> str:
    try:
        return f"₹{Decimal(str(value or 0)):,.2f}"
    except Exception:
        return f"₹{value}"


def _fmt_date(d) -> str:
    if isinstance(d, date):
        return d.strftime("%a, %d %b %Y")
    return str(d) if d else "—"


def _fmt_time(t) -> str:
    if isinstance(t, time):
        return t.strftime("%I:%M %p").lstrip("0")
    if isinstance(t, str) and len(t) >= 5:
        return t[:5]
    return str(t) if t else "—"


def _shell(title: str, preheader: str, body_html: str) -> str:
    """Wrap body content in the standard Signal Shift email shell."""
    support = settings.brand_support_email
    site = settings.frontend_base_url.rstrip("/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f6f8f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#121f00;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;font-size:1px;line-height:1px;color:#f6f8f4;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8f4;padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 32px rgba(0,73,0,0.06);">
        <tr>
          <td style="background:#0a0b0c;padding:28px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-family:'Bricolage Grotesque',Georgia,serif;font-size:22px;font-weight:700;letter-spacing:-0.01em;color:#ffffff;">
                    signal<span style="color:#b2f746;">·</span>shift
                  </div>
                </td>
                <td align="right" style="font-size:10px;letter-spacing:0.25em;color:#707a6a;text-transform:uppercase;">
                  Book · Play · Win
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 32px 8px 32px;">
            {body_html}
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 32px 32px;">
            <div style="border-top:1px solid #e4ead9;padding-top:20px;font-size:12px;color:#707a6a;line-height:1.6;">
              Need help? Reply to this email or reach us at <a href="mailto:{support}" style="color:#004900;text-decoration:none;font-weight:600;">{support}</a>.
              <br>
              <a href="{site}" style="color:#707a6a;text-decoration:none;">{site.replace('https://','').replace('http://','')}</a>
              &nbsp;·&nbsp; Made with <span style="color:#004900;">◆</span> in Tamil Nadu
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _btn(label: str, href: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;"><tr><td style="border-radius:999px;background:#b2f746;"><a href="{href}" style="display:inline-block;padding:14px 28px;font-size:14px;font-weight:700;color:#121f00;text-decoration:none;letter-spacing:0.01em;">{label}</a></td></tr></table>"""


def _kv_row(label: str, value: str) -> str:
    return f"""<tr><td style="padding:8px 0;font-size:13px;color:#707a6a;width:130px;vertical-align:top;">{label}</td><td style="padding:8px 0;font-size:14px;color:#121f00;font-weight:600;">{value}</td></tr>"""


def _headline(kicker: str, headline: str) -> str:
    return f"""
<div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.25em;color:#004900;text-transform:uppercase;margin-bottom:10px;">{kicker}</div>
<h1 style="font-family:'Bricolage Grotesque',Georgia,serif;font-size:26px;font-weight:700;line-height:1.2;margin:0 0 16px 0;color:#121f00;letter-spacing:-0.01em;">{headline}</h1>"""


# ─── Templates ───────────────────────────────────────────


def booking_created(*, user_name: str, turf_name: str, booking_date, start_time, end_time, final_price, booking_id: str, upi_vpa: str | None) -> tuple[str, str, str]:
    subject = f"Booking received · {turf_name}"
    site = settings.frontend_base_url.rstrip("/")
    upi_note = (
        f'<tr><td colspan="2" style="padding-top:20px;"><div style="background:#fef9e8;border:1px solid #f3e1a0;border-radius:12px;padding:14px 16px;font-size:13px;color:#7a5b00;line-height:1.55;"><strong>Awaiting payment.</strong> Complete UPI transfer to <strong>{upi_vpa}</strong> and submit the UTR in the app to confirm this booking.</div></td></tr>'
        if upi_vpa else ""
    )
    body = f"""
{_headline("Booking received", f"Hey {user_name.split()[0] if user_name else 'there'} — we've got you.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Your slot is held pending payment. Here's the snapshot:
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:8px 0 0 0;">
  {_kv_row("Turf", turf_name)}
  {_kv_row("Date", _fmt_date(booking_date))}
  {_kv_row("Time", f"{_fmt_time(start_time)} – {_fmt_time(end_time)}")}
  {_kv_row("Total", _money(final_price))}
  {_kv_row("Ref", booking_id[:8])}
  {upi_note}
</table>
{_btn("View booking", f"{site}/bookings")}
<p style="font-size:13px;color:#707a6a;line-height:1.6;margin:0;">Play smart. Arrive 10 minutes early. Bring the good vibes.</p>
"""
    text = f"Booking received for {turf_name} on {_fmt_date(booking_date)} {_fmt_time(start_time)}-{_fmt_time(end_time)}. Total {_money(final_price)}. Ref {booking_id[:8]}."
    return subject, _shell(subject, f"{turf_name} · {_fmt_date(booking_date)}", body), text


def booking_confirmed(*, user_name: str, turf_name: str, booking_date, start_time, end_time, final_price, booking_id: str) -> tuple[str, str, str]:
    subject = f"Confirmed · {turf_name} · {_fmt_date(booking_date)}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("You're in", f"Locked in, {user_name.split()[0] if user_name else 'champion'}.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Payment verified. Your booking is <strong style="color:#004900;">confirmed</strong>. The turf is yours.
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Turf", turf_name)}
  {_kv_row("Date", _fmt_date(booking_date))}
  {_kv_row("Time", f"{_fmt_time(start_time)} – {_fmt_time(end_time)}")}
  {_kv_row("Paid", _money(final_price))}
  {_kv_row("Ref", booking_id[:8])}
</table>
{_btn("See my bookings", f"{site}/bookings")}
<p style="font-size:13px;color:#707a6a;line-height:1.6;margin:0;">Change of plans? You can cancel from the app — refund rules depend on the turf's policy.</p>
"""
    text = f"Booking CONFIRMED for {turf_name} on {_fmt_date(booking_date)} {_fmt_time(start_time)}-{_fmt_time(end_time)}."
    return subject, _shell(subject, f"Confirmed · {turf_name}", body), text


def booking_cancelled(*, user_name: str, turf_name: str, booking_date, start_time, end_time, refund_amount, refund_pct: int | None, booking_id: str) -> tuple[str, str, str]:
    subject = f"Cancelled · {turf_name} · {_fmt_date(booking_date)}"
    site = settings.frontend_base_url.rstrip("/")
    refund_block = (
        f'<div style="background:#eefce0;border:1px solid #c3e69a;border-radius:12px;padding:14px 16px;font-size:13px;color:#2a4100;line-height:1.55;margin-top:20px;"><strong>Refund:</strong> {_money(refund_amount)} ({refund_pct or 0}% of booking) will be credited within 5–7 working days.</div>'
        if refund_amount and float(refund_amount) > 0
        else '<div style="background:#fdf1f1;border:1px solid #f3c3c3;border-radius:12px;padding:14px 16px;font-size:13px;color:#7a1f1f;line-height:1.55;margin-top:20px;"><strong>No refund.</strong> This cancellation falls outside the refund window of the turf policy.</div>'
    )
    body = f"""
{_headline("Booking cancelled", "No sweat — stuff happens.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Hey {user_name.split()[0] if user_name else 'there'}, your booking has been cancelled.
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Turf", turf_name)}
  {_kv_row("Date", _fmt_date(booking_date))}
  {_kv_row("Time", f"{_fmt_time(start_time)} – {_fmt_time(end_time)}")}
  {_kv_row("Ref", booking_id[:8])}
</table>
{refund_block}
{_btn("Book another slot", f"{site}/turfs")}
"""
    text = f"Booking cancelled for {turf_name} on {_fmt_date(booking_date)}. Refund: {_money(refund_amount)}."
    return subject, _shell(subject, f"Cancelled · {turf_name}", body), text


def payment_verified(*, user_name: str, amount, utr: str | None, booking_ref: str, turf_name: str) -> tuple[str, str, str]:
    subject = f"Payment verified · {_money(amount)}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("Payment received", f"Thanks, {user_name.split()[0] if user_name else 'champion'} — we've got it.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Your UPI transfer has been verified against your booking.
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Amount", _money(amount))}
  {_kv_row("UTR", utr or "—")}
  {_kv_row("Booking", f"{turf_name} · {booking_ref[:8]}")}
</table>
{_btn("See my bookings", f"{site}/bookings")}
"""
    text = f"Payment of {_money(amount)} verified. UTR: {utr or '—'}. Booking: {booking_ref[:8]}."
    return subject, _shell(subject, "Payment verified", body), text


def payment_rejected(*, user_name: str, amount, utr: str | None, booking_ref: str, turf_name: str, reason: str) -> tuple[str, str, str]:
    subject = f"Payment issue · {turf_name}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("Payment not verified", "We couldn't confirm this transfer.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Hey {user_name.split()[0] if user_name else 'there'}, our team reviewed the UTR for your booking and couldn't match it to a received transfer.
</p>
<div style="background:#fdf1f1;border:1px solid #f3c3c3;border-radius:12px;padding:14px 16px;font-size:14px;color:#7a1f1f;line-height:1.55;margin:0 0 20px 0;">
  <strong>Reason:</strong> {reason}
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Amount", _money(amount))}
  {_kv_row("UTR", utr or "—")}
  {_kv_row("Booking", f"{turf_name} · {booking_ref[:8]}")}
</table>
<p style="font-size:14px;line-height:1.6;color:#404a3b;margin:20px 0 0 0;">
If you believe this is a mistake, please resubmit the correct UTR from the booking page or reach out to support.
</p>
{_btn("Resubmit UTR", f"{site}/bookings")}
"""
    text = f"Payment could not be verified. Reason: {reason}. Amount: {_money(amount)}. Booking: {booking_ref[:8]}."
    return subject, _shell(subject, f"Payment issue · {turf_name}", body), text


def team_member_added(*, new_member_name: str, team_name: str, inviter_name: str) -> tuple[str, str, str]:
    subject = f"You're on team {team_name}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("New crew", f"Welcome to {team_name}.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Hey {new_member_name.split()[0] if new_member_name else 'there'} — <strong>{inviter_name}</strong> added you to the <strong>{team_name}</strong> roster.
</p>
<p style="font-size:14px;line-height:1.6;color:#707a6a;margin:0 0 8px 0;">
Jump in, check the schedule, and start booking slots together.
</p>
{_btn(f"Open {team_name}", f"{site}/teams")}
"""
    text = f"{inviter_name} added you to team {team_name}."
    return subject, _shell(subject, f"Welcome to {team_name}", body), text


def team_invitation(*, invitee_email: str, team_name: str, inviter_name: str) -> tuple[str, str, str]:
    subject = f"{inviter_name} invited you to {team_name}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("You're invited", f"Join {team_name} on Signal Shift.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
<strong>{inviter_name}</strong> wants you on the roster. Sign up with this email ({invitee_email}) and you'll automatically be added when you log in.
</p>
{_btn("Create my account", f"{site}/login")}
<p style="font-size:13px;color:#707a6a;line-height:1.6;margin:0;">Already on Signal Shift? Just log in — we'll add you to the team.</p>
"""
    text = f"{inviter_name} invited you to team {team_name}. Sign up at {site}/login with {invitee_email}."
    return subject, _shell(subject, f"Invited to {team_name}", body), text


def tournament_registered(*, captain_name: str, tournament_name: str, team_name: str, starts_on, entry_fee, payment_status: str) -> tuple[str, str, str]:
    subject = f"Registered · {tournament_name}"
    site = settings.frontend_base_url.rstrip("/")
    fee_row = _kv_row("Entry fee", _money(entry_fee)) if entry_fee and float(entry_fee) > 0 else ""
    status_badge = (
        '<span style="display:inline-block;background:#eefce0;color:#2a4100;border:1px solid #c3e69a;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">Paid</span>'
        if payment_status == "paid"
        else '<span style="display:inline-block;background:#fef9e8;color:#7a5b00;border:1px solid #f3e1a0;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">Payment due</span>'
    )
    body = f"""
{_headline("Registration in", f"{team_name} is on the bracket.")}
<p style="font-size:15px;line-height:1.6;color:#404a3b;margin:0 0 20px 0;">
Hey {captain_name.split()[0] if captain_name else 'captain'}, your team is registered for <strong>{tournament_name}</strong>. {status_badge}
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Tournament", tournament_name)}
  {_kv_row("Team", team_name)}
  {_kv_row("Starts", _fmt_date(starts_on))}
  {fee_row}
</table>
{_btn("View tournament", f"{site}/tournaments")}
"""
    text = f"{team_name} registered for {tournament_name}, starts {_fmt_date(starts_on)}."
    return subject, _shell(subject, f"Registered · {tournament_name}", body), text


def admin_new_booking(*, user_name: str, user_email: str, user_phone: str | None, turf_name: str, booking_date, start_time, end_time, final_price, booking_id: str) -> tuple[str, str, str]:
    subject = f"New booking · {turf_name} · {_fmt_date(booking_date)}"
    site = settings.frontend_base_url.rstrip("/")
    body = f"""
{_headline("Admin alert", f"New booking on {turf_name}.")}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e4ead9;border-radius:14px;padding:4px 18px;margin:0;">
  {_kv_row("Customer", f"{user_name} ({user_email})")}
  {_kv_row("Phone", user_phone or "—")}
  {_kv_row("Turf", turf_name)}
  {_kv_row("Date", _fmt_date(booking_date))}
  {_kv_row("Time", f"{_fmt_time(start_time)} – {_fmt_time(end_time)}")}
  {_kv_row("Amount", _money(final_price))}
  {_kv_row("Ref", booking_id[:8])}
</table>
{_btn("Open admin panel", f"{site.replace('signalshift.in','admin.signalshift.in')}/dashboard/bookings")}
"""
    text = f"New booking: {user_name} ({user_email}) booked {turf_name} on {_fmt_date(booking_date)} {_fmt_time(start_time)}-{_fmt_time(end_time)}. Amount: {_money(final_price)}."
    return subject, _shell(subject, f"New booking · {turf_name}", body), text
