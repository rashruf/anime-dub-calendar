# Anime English Dub Calendar → iOS Agenda

GitHub Actions haalt elk uur de Engelse dub-tijden op bij
[AnimeSchedule.net](https://animeschedule.net) en GitHub Pages serveert het
`.ics`-bestand. Geen server, geen kosten.

## Abonneren op iPhone
Instellingen → Agenda → Accounts → Voeg account toe → Overig →
**Voeg agenda-abonnement toe**:
```
https://rashruf.github.io/anime-dub-calendar/anime-dubs.ics
```

## Instellingen in deze repo
- **Secret** `ANIMESCHEDULE_TOKEN`: app token van animeschedule.net (accountinstellingen → API).
- **Variable** `MY_ROUTES` (optioneel): bv. `one-piece,sousou-no-frieren`. Maakt ook
  `mijn-dubs.ics` met alleen die titels. De route is het laatste deel van de URL op
  animeschedule.net/anime/...
- **Pages**: Deploy from a branch → `main` / `/docs`.

## Goed om te weten
- Er wordt alleen gecommit als het schema echt verandert.
- Mislukt de API, dan blijft de vorige agenda online staan.
- Stabiele UID per aflevering: verschuift een release, dan verplaatst het event.
- Uitgestelde afleveringen krijgen ⏸ in de titel; events staan op "vrij".
- Lokaal testen: `pip install requests`, `$env:ANIMESCHEDULE_TOKEN="..."`,
  `python build.py`, bekijk `docs\anime-dubs.ics`.
