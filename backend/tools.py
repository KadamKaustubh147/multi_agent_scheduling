import os
import json
from datetime import date, timedelta
from langchain_core.tools import tool
from dateutil import parser as date_parser
from httpx import post as http_post
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("NOTIFICATION_WEBHOOK_URL", "")

# ─── In-memory booking store ─────────────────────────────────────────────────
SLOTS = [f"{h}:00" for h in range(9, 18)]  # 09:00 to 17:00

_bookings: dict[str, set[str]] = {
    (date.today() + timedelta(days=1)).isoformat(): {"10:00", "14:00"}, # Pre-booked for testing
    (date.today() + timedelta(days=2)).isoformat(): {"09:00"},
}
_booking_log: list[dict] = []

# ─── Date normalisation ──────────────────────────────────────────────────────

def resolve_date(raw: str) -> str:
    """'tomorrow' / 'next monday' / '2025-07-04' → YYYY-MM-DD"""
    today = date.today()
    low = raw.lower().strip()

    if low == "today": return today.isoformat()
    if low == "tomorrow": return (today + timedelta(days=1)).isoformat()
    if "day after tomorrow" in low: return (today + timedelta(days=2)).isoformat()

    if low.startswith("next "):
        weekdays = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
        target = weekdays.get(low.replace("next ", "").strip())
        if target is not None:
            days_ahead = (target - today.weekday()) % 7 or 7
            return (today + timedelta(days=days_ahead)).isoformat()

    try:
        return date_parser.parse(raw, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError): pass

    try:
        date.fromisoformat(raw)
        return raw
    except ValueError: pass

    raise ValueError(f"Cannot parse '{raw}'. Use YYYY-MM-DD or 'tomorrow'.")

# ─── Tools ───────────────────────────────────────────────────────────────────

@tool
def check_availability(date_input: str) -> str:
    """Check which time slots are free on a date."""
    try:
        resolved = resolve_date(date_input)
    except ValueError as e:
        return str(e)

    if resolved < date.today().isoformat():
        return f"{resolved} is in the past — pick a future date."

    taken = _bookings.get(resolved, set())
    free  = [s for s in SLOTS if s not in taken]

    if not free:
        return f"All slots on {resolved} are booked. Try another date."
    return f"Available on {resolved}: {', '.join(free)}"


@tool
def reserve_slot(date_input: str, time: str, email: str) -> str:
    """Reserve an appointment slot. Returns confirmation or negotiates."""
    try:
        resolved = resolve_date(date_input)
    except ValueError as e:
        return str(e)

    if resolved < date.today().isoformat():
        return f"Cannot book in the past ({resolved})."
    if time not in SLOTS:
        return f"'{time}' is invalid. Valid slots: {', '.join(SLOTS)}"

    taken = _bookings.get(resolved, set())
    if time in taken:
        free = [s for s in SLOTS if s not in taken]
        hint = f" Alternatives: {', '.join(free)}." if free else " No other slots that day."
        return f"{time} on {resolved} is already taken.{hint}"

    _bookings.setdefault(resolved, set()).add(time)
    booking = {"date": resolved, "time": time, "email": email, "id": len(_booking_log) + 1}
    _booking_log.append(booking)

    return (
        f"Booked! Date: {resolved} Time: {time} Email: {email} ID: {booking['id']}\n"
        f"Now call send_booking_notification to confirm."
    )


@tool
def send_booking_notification(email: str, details: str) -> str:
    """Send a booking confirmation (real webhook or mock). `details` must be a JSON
    string with keys "date", "time", and "id" — the confirmation message sent to the
    user will explicitly state the slot that was booked."""
    # Pull the slot info out of the details JSON so the email/webhook body can
    # state plainly what was booked, instead of just carrying a raw JSON blob.
    slot_date, slot_time, booking_id = None, None, None
    try:
        parsed = json.loads(details)
        slot_date = parsed.get("date")
        slot_time = parsed.get("time")
        booking_id = parsed.get("id")
    except (json.JSONDecodeError, TypeError):
        pass

    if slot_date and slot_time:
        friendly = f"Your appointment is confirmed for {slot_date} at {slot_time}."
        if booking_id is not None:
            friendly += f" (Booking ID: {booking_id})"
    else:
        # Fall back to the raw details if parsing failed for some reason
        friendly = f"Your appointment is confirmed. Details: {details}"

    payload = {
        "event": "booking_confirmation",
        "email": email,
        "date": slot_date,
        "time": slot_time,
        "id": booking_id,
        "message": friendly,
    }

    if WEBHOOK_URL:
        try:
            http_post(WEBHOOK_URL, json=payload, timeout=10)
            return f"Notification sent to {email}. {friendly}"
        except Exception as e:
            return f"Webhook failed ({e}), but booking is saved. {friendly}"

    print(f"[MOCK NOTIFICATION] To: {email} | {friendly}")
    return f"Confirmation queued for {email} (mock — set NOTIFICATION_WEBHOOK_URL for real delivery). {friendly}"


ALL_TOOLS = [check_availability, reserve_slot, send_booking_notification]