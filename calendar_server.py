"""HTTP server that serves .ics calendar subscriptions for training plans."""

import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ["LU", "MA", "MI", "JU", "VI", "SA", "DO"]


def _escape_ics(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _fold_line(line: str) -> str:
    """Fold long lines per RFC 5545 (max 75 octets per line)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts = []
    while len(encoded) > 75:
        cut = 75 if not parts else 74
        chunk = encoded[:cut]
        while chunk[-1] & 0xC0 == 0x80:
            chunk = chunk[:-1]
            cut = len(chunk)
        parts.append(chunk.decode("utf-8"))
        encoded = encoded[cut:]
    if encoded:
        parts.append(encoded.decode("utf-8"))
    return "\r\n ".join(parts)


def generate_ics(plan: dict, user_name: str = "") -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GarminCoach//Bot//ES",
        f"X-WR-CALNAME:Entrenamiento{' — ' + user_name if user_name else ''}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    sessions = plan.get("sessions", [])
    valid_from = plan.get("valid_from", datetime.now().strftime("%Y-%m-%d"))
    weeks = plan.get("weeks", 4)
    plan_id = plan.get("created_at", valid_from)

    start_date = datetime.strptime(valid_from, "%Y-%m-%d")

    for i, session in enumerate(sessions):
        weekday = session.get("weekday", 0)
        time_str = session.get("time", "18:00")
        duration = session.get("duration_minutes", 60)
        title = session.get("title", "Entrenamiento")
        description = session.get("description", "")

        days_ahead = weekday - start_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        event_date = start_date + timedelta(days=days_ahead)

        hour, minute = map(int, time_str.split(":"))
        event_start = event_date.replace(hour=hour, minute=minute, second=0)
        event_end = event_start + timedelta(minutes=duration)

        uid = f"gc-{i}-{plan_id}@garmincoach"

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(f"DTSTART:{event_start.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"DTEND:{event_end.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"SUMMARY:{_escape_ics(title)}")
        if description:
            lines.append(f"DESCRIPTION:{_escape_ics(description)}")
        lines.append(f"RRULE:FREQ=WEEKLY;COUNT={weeks}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    folded = [_fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


class _CalendarHandler(BaseHTTPRequestHandler):
    user_manager = None

    def do_GET(self):
        match = re.match(r"^/cal/([a-f0-9]+)\.ics$", self.path)
        if not match:
            self.send_response(404)
            self.end_headers()
            return

        token = match.group(1)

        if not self.user_manager:
            self.send_response(500)
            self.end_headers()
            return

        telegram_id = self.user_manager.find_user_by_calendar_token(token)
        if not telegram_id:
            self.send_response(404)
            self.end_headers()
            return

        plan = self.user_manager.get_plan(telegram_id)
        if not plan:
            self.send_response(404)
            self.end_headers()
            return

        profile = self.user_manager.get_profile(telegram_id)
        ics = generate_ics(plan, user_name=profile[:30] if profile else "")

        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(ics.encode("utf-8"))

    def log_message(self, format, *args):
        logger.info(format, *args)


def parse_plan_json(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def next_monday() -> str:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).isoformat()


def start_calendar_server(user_manager, port: int = 8080) -> HTTPServer:
    _CalendarHandler.user_manager = user_manager
    server = HTTPServer(("0.0.0.0", port), _CalendarHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Calendar server started on port %d", port)
    return server
