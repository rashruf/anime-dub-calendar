"""
Bouwt de agenda-bestanden in docs/ (wordt door GitHub Pages geserveerd).

    docs/anime-dubs.ics  -> alle Engelse dubs
    docs/mijn-dubs.ics   -> alleen de titels in MY_ROUTES (optioneel)

Omgevingsvariabelen:
    ANIMESCHEDULE_TOKEN  verplicht (GitHub secret)
    MY_ROUTES            optioneel, komma-gescheiden, bv. "one-piece,sousou-no-frieren"
"""
import os
import pathlib

import dubcal

out = pathlib.Path("docs")
out.mkdir(exist_ok=True)

token = os.environ["ANIMESCHEDULE_TOKEN"]
items = dubcal.fetch_range(
    token,
    int(os.environ.get("WEEKS_BACK", "1")),
    int(os.environ.get("WEEKS_AHEAD", "3")),
)
if not items:
    raise SystemExit("Geen data van de API ontvangen; bestaande agenda blijft staan.")


def write(name: str, ics: str) -> None:
    (out / name).write_text(ics, encoding="utf-8", newline="")
    print(f"{name}: {ics.count('BEGIN:VEVENT')} afleveringen")


write("anime-dubs.ics", dubcal.build_ics(items))

routes = {r.strip() for r in os.environ.get("MY_ROUTES", "").split(",") if r.strip()}
if routes:
    write("mijn-dubs.ics", dubcal.build_ics(items, routes, cal_name="Mijn anime dubs"))
