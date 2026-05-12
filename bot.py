async def fetch_matches(iso_date: str, label: str) -> list:
    if not ODDSPAPI_KEY:
        raise RuntimeError("ODDSPAPI_KEY manquante (clé The Odds API)")

    paris_tz = pytz.timezone("Europe/Paris")
    SPORT_KEYS = {
        "soccer_france_ligue_1": "Ligue 1",
        "soccer_france_ligue_2": "Ligue 2",
        "soccer_epl": "Premier League",
        "soccer_england_championship": "Championship",
        "soccer_spain_la_liga": "La Liga",
        "soccer_italy_serie_a": "Serie A",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_uefa_champions_league": "Champions League",
        "soccer_uefa_europa_league": "Europa League",
        "soccer_uefa_europa_conf_league": "Conference League",
        "soccer_portugal_primeira_liga": "Primeira Liga",
        "soccer_netherlands_eredivisie": "Eredivisie",
    }

    matches = []
    start = f"{iso_date}T00:00:00Z"
    end = f"{iso_date}T23:59:59Z"

    async with aiohttp.ClientSession() as session:
        for sport_key, comp_name in SPORT_KEYS.items():
            params = {
                "apiKey": ODDSPAPI_KEY,
                "regions": "eu",
                "markets": "h2h",
                "oddsFormat": "decimal",
                "commenceTimeFrom": start,
                "commenceTimeTo": end,
            }
            try:
                async with session.get(
                    f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                    params=params, timeout=15
                ) as resp:
                    if resp.status != 200:
                        txt = await resp.text()
                        log.warning(f"The Odds API {sport_key} {resp.status}: {txt[:100]}")
                        continue
                    data = await resp.json()
                    log.info(f"The Odds API {sport_key}: {len(data)} matchs")
            except Exception as e:
                log.warning(f"The Odds API error {sport_key}: {e}")
                continue

            for event in data:
                try:
                    dt = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
                    dt_p = dt.astimezone(paris_tz)
                    if dt_p.strftime("%Y-%m-%d") != iso_date:
                        continue
                    heure = dt_p.strftime("%H:%M")
                except:
                    continue

                home = event.get("home_team", "?")
                away = event.get("away_team", "?")

                # Extraire cotes bet365 (ou premier bookmaker eu)
                ch = cd = ca = bk_used = None
                for bk in event.get("bookmakers", []):
                    if bk.get("key") not in ["bet365", "unibet", "pinnacle"]:
                        continue
                    for market in bk.get("markets", []):
                        if market.get("key") != "h2h":
                            continue
                        outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                        ch = outcomes.get("Home")
                        cd = outcomes.get("Draw")
                        ca = outcomes.get("Away")
                        bk_used = bk.get("key")
                        if ch and ca:
                            break
                    if ch: break

                if ch:
                    matches.append({
                        "home": home, "away": away, "competition": comp_name,
                        "date": label, "heure": heure,
                        "cote_home": ch, "cote_draw": cd, "cote_away": ca,
                        "bookmaker": bk_used or "?",
                    })

    matches.sort(key=lambda m: m.get("heure", "99:99"))
    log.info(f"The Odds API: {len(matches)} matchs pour {iso_date}")
    return matches[:12]
