"""
dubcal.py - Bouwt een iCalendar (.ics) feed met Engelse dub-releases
op basis van de AnimeSchedule.net API v3 (/timetables/dub).

Alleen afhankelijk van 'requests'. Wordt gebruikt door build.py.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

API_BASE = "https://animeschedule.net/api/v3"
SITE_BASE = "https://animeschedule.net/anime"
DEFAULT_LENGTH_MIN = 24
USER_AGENT = "anime-dub-calendar/1.0"

log = logging.getLogger("dubcal")


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
def fetch_week(token: str, year: int, week: int) -> list[dict]:
    """Haalt de dub-timetable van één ISO-week op. Tijden komen terug in UTC."""
    resp = requests.get(
        f"{API_BASE}/timetables/dub",
        params={"year": year, "week": week, "tz": "UTC"},
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_range(token: str, weeks_back: int = 1, weeks_ahead: int = 3) -> list[dict]:
    """Haalt meerdere weken op (vorige week t/m een paar weken vooruit)."""
    today = datetime.now(timezone.utc).date()
    items: list[dict] = []
    seen_weeks = set()
    for offset in range(-weeks_back, weeks_ahead + 1):
        iso = (today + timedelta(weeks=offset)).isocalendar()
        key = (iso[0], iso[1])
        if key in seen_weeks:
            continue
        seen_weeks.add(key)
        try:
            items.extend(fetch_week(token, iso[0], iso[1]))
        except requests.RequestException as exc:
            log.warning("Week %s-%s ophalen mislukt: %s", iso[0], iso[1], exc)
    return items


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545: regels max 75 octets, vervolgregels beginnen met een spatie."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, chunk, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk, limit = b"", 74  # 1 octet gaat naar de voorloopspatie
        chunk += b
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


SERVICE_NAMES = {
    "crunchyroll": "Crunchyroll",
    "netflix": "Netflix",
    "hulu": "Hulu",
    "disney": "Disney+",
    "disneyplus": "Disney+",
    "amazon": "Prime Video",
    "primevideo": "Prime Video",
    "apple": "Apple TV",
    "youtube": "YouTube",
    "bilibili": "Bilibili",
    "hidive": "HIDIVE",
    "adn": "ADN",
    "max": "Max",
    "hbo": "Max",
    "hbomax": "Max",
    "funimation": "Funimation",
    "tubi": "Tubi",
    "retrocrush": "RetroCrush",
    "aniplus": "Aniplus",
    "muse": "Muse Asia",
    "anione": "Ani-One",
    "iqiyi": "iQIYI",
}

# Volgorde waarin diensten getoond worden (rest daarna alfabetisch)
SERVICE_ORDER = ["Crunchyroll", "Netflix", "HIDIVE", "Prime Video", "Disney+", "Max", "Hulu", "ADN"]

# Aparte agenda's per dienst: (bestandsnaam, dienst, agendanaam, kleur).
# Een aflevering komt in de feed van de eerste dienst uit SERVICE_ORDER die hij heeft;
# alles zonder een van deze diensten komt in 'overig'.
FEEDS = [
    ("crunchyroll", "Crunchyroll", "Dubs · Crunchyroll", "#E5262B"),  # rood
    ("netflix", "Netflix", "Dubs · Netflix", "#1C1C1E"),              # zwart
    ("hidive", "HIDIVE", "Dubs · HIDIVE", "#AF52DE"),                 # paars
    ("prime-video", "Prime Video", "Dubs · Prime Video", "#34C759"),  # groen
    ("disney", "Disney+", "Dubs · Disney+", "#007AFF"),               # blauw
]
OTHER_FEED = ("overig", None, "Dubs · Overig", "#8E8E93")             # grijs


def primary_feed(item: dict) -> str:
    """Bepaalt in welke dienst-feed een aflevering hoort."""
    names = {n for n, _ in _streams(item.get("streams"))}
    for slug, service, _, _ in FEEDS:
        if service in names:
            return slug
    return OTHER_FEED[0]


def _streams(streams) -> list[tuple[str, str]]:
    """Geeft [(nette naam, url), ...] terug; 'streams' kan een dict of lijst zijn."""
    pairs: list[tuple[str, str]] = []
    if isinstance(streams, dict):
        raw = [(k, v) for k, v in streams.items() if isinstance(v, str) and v]
    elif isinstance(streams, list):
        raw = [((s.get("platform") or s.get("name") or "stream"), (s.get("url") or s.get("link") or ""))
               for s in streams if isinstance(s, dict)]
    else:
        raw = []
    seen = set()
    for key, url in raw:
        name = SERVICE_NAMES.get(str(key).lower().replace(" ", "").replace("+", ""), str(key).title())
        if name in seen or not url:
            continue
        seen.add(name)
        pairs.append((name, url if url.startswith("http") else "https://" + url))
    rank = {n: i for i, n in enumerate(SERVICE_ORDER)}
    pairs.sort(key=lambda p: (rank.get(p[0], len(rank)), p[0]))
    return pairs


# ----------------------------------------------------------------------------
# ICS
# ----------------------------------------------------------------------------
def build_ics(items: list[dict], include_routes: set[str] | None = None,
              cal_name: str = "Anime English Dubs", color: str | None = None) -> str:
    now = _fmt(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//anime-dub-calendar//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(cal_name)}",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    if color:
        lines.append(f"X-APPLE-CALENDAR-COLOR:{color}")  # beginkleur in iOS/macOS

    seen_uids = set()
    for it in items:
        route = (it.get("route") or "").strip()
        if include_routes and route not in include_routes:
            continue

        start = _parse_dt(it.get("episodeDate"))
        if not start:
            continue

        title = it.get("english") or it.get("title") or it.get("romaji") or route or "Onbekend"
        ep = it.get("episodeNumber")
        total = it.get("episodes")
        length = it.get("lengthMin") or DEFAULT_LENGTH_MIN
        end = start + timedelta(minutes=int(length))

        status = (it.get("airingStatus") or it.get("status") or "").lower()
        delayed = it.get("delayedText") or ("delayed" in status and "Uitgesteld")

        summary = f"{title} (Dub)"
        if ep:
            summary += f" – Ep {ep}" + (f"/{total}" if total else "")
        if delayed:
            summary = f"⏸ {summary}"

        streams = _streams(it.get("streams"))
        services = ", ".join(n for n, _ in streams)

        desc = []
        if services:
            desc.append(f"Te zien op: {services}")
        if delayed:
            desc.append(f"Status: {delayed}")
        if it.get("title") and it.get("title") != title:
            desc.append(f"Titel: {it['title']}")
        if streams:
            desc.append("")
            desc.extend(f"{n}: {u}" for n, u in streams)
        page = f"{SITE_BASE}/{route}" if route else ""
        if page:
            desc.append(page)

        uid_src = f"{route or title}-ep{ep}-dub"
        uid = hashlib.sha1(uid_src.encode()).hexdigest() + "@anime-dub-calendar"
        if uid in seen_uids:
            continue
        seen_uids.add(uid)

        ev = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{_fmt(start)}",
            f"DTEND:{_fmt(end)}",
            f"SUMMARY:{_escape(summary)}",
        ]
        if services:
            ev.append(f"LOCATION:{_escape(services)}")  # iOS toont dit direct onder de titel
        if desc:
            ev.append(f"DESCRIPTION:{_escape(chr(10).join(desc))}")
        if page:
            ev.append(f"URL:{page}")
        ev.append("TRANSP:TRANSPARENT")  # blokkeert je agenda niet als 'bezet'
        ev.append("END:VEVENT")
        lines.extend(ev)

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def generate(token: str | None = None, include_routes: set[str] | None = None) -> str:
    token = token or os.environ["ANIMESCHEDULE_TOKEN"]
    weeks_back = int(os.environ.get("WEEKS_BACK", "1"))
    weeks_ahead = int(os.environ.get("WEEKS_AHEAD", "3"))
    return build_ics(fetch_range(token, weeks_back, weeks_ahead), include_routes)
