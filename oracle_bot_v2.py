import os
import json
import re
import asyncio
import logging
import html
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger("oracle_bot_v2")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS", "").replace("\n", ",").split(",") if k.strip()]
ODDS_API_KEY = (
    os.getenv("ODDSPAPI_KEY", "").strip()
    or os.getenv("ODDS_API_KEY", "").strip()
    or os.getenv("THE_ODDS_API_KEY", "").strip()
)
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
BANKROLL = float(os.getenv("BANKROLL", "100"))
DB_FILE = Path(os.getenv("DB_FILE", "oracle_db.json"))
PARIS_TZ = pytz.timezone("Europe/Paris")
GROQ_IDX = 0

SPORT_KEYS = [
    "soccer_france_ligue_1",
    "soccer_france_ligue_2",
    "soccer_epl",
    "soccer_england_championship",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_uefa_champs_league",
    "soccer_uefa_champions_league",
    "soccer_uefa_europa_league",
    "soccer_uefa_europa_conference_league",
    "soccer_uefa_europa_conf_league",
]

AGENTS = [
    ("tact", "Tacticien", "🧠"),
    ("stat", "Statisticien", "📊"),
    ("phys", "Médecin/Fatigue", "🏃"),
    ("scout", "Ancien Scout", "🧓"),
    ("market", "Marché/Value", "💰"),
    ("psy", "Psychologue", "🎭"),
    ("tempo", "Rythme/Buts", "⚽"),
    ("risk", "Red Team", "🛡️"),
    ("judge", "Juge", "⚖️"),
    ("prof", "Professeur Final", "🎓"),
]

SYSTEM_BY_AGENT = {
    "tact": "Tu es tacticien football. Analyse styles, pressing, transitions, compatibilité des équipes. 75 mots max, concret.",
    "stat": "Tu es statisticien football. Analyse forme, xG approximatif, dynamique, solidité, variance. 75 mots max, concret.",
    "phys": "Tu es médecin/coach physique. Analyse fatigue, rotation, blessures probables, calendrier, intensité. 65 mots max.",
    "scout": "Tu es ancien scout. Repère pièges, profils historiques, motivation cachée, match-up mental. 65 mots max.",
    "market": "Tu es analyste value betting. Compare probabilités implicites, cotes et risque de piège. 75 mots max.",
    "psy": "Tu es psychologue sportif. Motivation, pression, enjeu, domicile, contexte émotionnel. 60 mots max.",
    "tempo": "Tu es expert marchés buts/BTTS. Analyse rythme attendu, chances de Over/Under 2.5, BTTS Oui/Non. 75 mots max.",
    "risk": "Tu es red team. Donne le meilleur contre-argument et pourquoi ce pari peut perdre. 65 mots max.",
    "judge": "Tu es juge arbitre. Résume les signaux utiles et élimine les paris faibles. 90 mots max.",
}


def esc(x: Any) -> str:
    return html.escape(str(x), quote=False)


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def db_load() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scans": {}, "lessons": []}


def db_save(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def next_key() -> str:
    global GROQ_IDX
    if not GROQ_KEYS:
        raise RuntimeError("GROQ_KEYS manquante")
    key = GROQ_KEYS[GROQ_IDX % len(GROQ_KEYS)]
    GROQ_IDX += 1
    return key


def target_day() -> Dict[str, Any]:
    now = datetime.now(PARIS_TZ)
    target = now + timedelta(days=1) if now.hour >= 21 else now
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    mode = "DEMAIN" if target.date() != now.date() else "AUJOURD'HUI"
    return {
        "mode": mode,
        "label": f"{jours[target.weekday()]} {target.day} {mois[target.month - 1]} {target.year}",
        "key": target.strftime("%Y-%m-%d"),
        "iso_date": target.strftime("%Y-%m-%d"),
        "scanned_at": now.strftime("%Y-%m-%d %H:%M"),
    }


async def groq(system: str, user: str, max_tokens: int = 500, temperature: float = 0.45, json_mode: bool = False) -> str:
    payload: Dict[str, Any] = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {next_key()}", "Content-Type": "application/json"}
    last_error = ""
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=45) as resp:
                    raw = await resp.text()
                    if resp.status == 429:
                        await asyncio.sleep(6 + attempt * 6)
                        continue
                    if resp.status >= 400:
                        last_error = raw[:300]
                        await asyncio.sleep(2)
                        continue
                    data = json.loads(raw)
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(2)
    raise RuntimeError(f"Groq indisponible: {last_error[:180]}")


def outcome_price(outcomes: List[Dict[str, Any]], *names: str) -> Optional[float]:
    wanted = [n.lower() for n in names if n]
    for o in outcomes:
        name = str(o.get("name", "")).lower()
        if name in wanted:
            try:
                return float(o.get("price"))
            except Exception:
                return None
    return None


def extract_markets(event: Dict[str, Any], home: str, away: str) -> Dict[str, Any]:
    markets = {
        "h2h_home": None, "h2h_draw": None, "h2h_away": None,
        "over25": None, "under25": None,
        "btts_yes": None, "btts_no": None,
        "bookmaker": "",
    }
    preferred = ["pinnacle", "bet365", "unibet", "betfair_ex_eu", "williamhill", "bwin"]
    bookmakers = event.get("bookmakers", []) or []
    bookmakers.sort(key=lambda b: preferred.index(b.get("key")) if b.get("key") in preferred else 99)

    for bookmaker in bookmakers:
        local = dict(markets)
        for market in bookmaker.get("markets", []) or []:
            key = market.get("key")
            outcomes = market.get("outcomes", []) or []
            if key == "h2h":
                local["h2h_home"] = outcome_price(outcomes, home, "Home")
                local["h2h_draw"] = outcome_price(outcomes, "Draw", "Nul")
                local["h2h_away"] = outcome_price(outcomes, away, "Away")
            elif key == "totals":
                for o in outcomes:
                    point = str(o.get("point", ""))
                    name = str(o.get("name", "")).lower()
                    if point == "2.5" and name == "over":
                        local["over25"] = float(o.get("price"))
                    if point == "2.5" and name == "under":
                        local["under25"] = float(o.get("price"))
            elif key == "btts":
                local["btts_yes"] = outcome_price(outcomes, "Yes", "Oui")
                local["btts_no"] = outcome_price(outcomes, "No", "Non")
        if local["h2h_home"] or local["over25"] or local["btts_yes"]:
            local["bookmaker"] = bookmaker.get("title") or bookmaker.get("key", "bookmaker")
            return local
    return markets


async def fetch_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not ODDS_API_KEY:
        raise RuntimeError("ODDSPAPI_KEY / ODDS_API_KEY manquante")
    start = f"{iso_date}T00:00:00Z"
    end = f"{iso_date}T23:59:59Z"
    matches: List[Dict[str, Any]] = []
    seen = set()
    async with aiohttp.ClientSession() as session:
        for sport in SPORT_KEYS:
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "eu",
                "markets": "h2h,totals,btts",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
                "commenceTimeFrom": start,
                "commenceTimeTo": end,
            }
            try:
                async with session.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds", params=params, timeout=18) as resp:
                    if resp.status != 200:
                        log.warning("Odds API %s status=%s", sport, resp.status)
                        continue
                    data = await resp.json()
            except Exception as e:
                log.warning("Odds API error %s: %s", sport, e)
                continue

            for event in data:
                home = event.get("home_team") or "?"
                away = event.get("away_team") or "?"
                eid = event.get("id") or f"{home}-{away}-{event.get('commence_time')}"
                if eid in seen:
                    continue
                seen.add(eid)
                try:
                    dt = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception:
                    continue
                if dt.strftime("%Y-%m-%d") != iso_date:
                    continue
                markets = extract_markets(event, home, away)
                if not any(markets.get(k) for k in ["h2h_home", "over25", "under25", "btts_yes", "btts_no"]):
                    continue
                matches.append({
                    "id": eid,
                    "home": home,
                    "away": away,
                    "competition": sport.replace("soccer_", "").replace("_", " ").title(),
                    "date": label,
                    "heure": dt.strftime("%H:%M"),
                    **markets,
                })
    matches.sort(key=lambda m: (m.get("heure", "99:99"), m.get("competition", "")))
    return matches[:12]


def build_candidates(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    home, away = match["home"], match["away"]
    raw = [
        ("h2h", f"Victoire {home}", match.get("h2h_home")),
        ("h2h", "Match nul", match.get("h2h_draw")),
        ("h2h", f"Victoire {away}", match.get("h2h_away")),
        ("total", "Plus de 2.5 buts", match.get("over25")),
        ("total", "Moins de 2.5 buts", match.get("under25")),
        ("btts", "Les deux équipes marquent — Oui", match.get("btts_yes")),
        ("btts", "Les deux équipes marquent — Non", match.get("btts_no")),
    ]
    cands = []
    for typ, name, odds in raw:
        try:
            price = float(odds)
        except Exception:
            continue
        if 1.20 <= price <= 6.00:
            cands.append({"type": typ, "pari": name, "odds": round(price, 2), "implied_prob": round(100 / price, 1)})
    return cands


def market_from_pari(pari: str) -> str:
    p = pari.lower()
    if "2.5" in p or "but" in p or "moins de" in p or "plus de" in p:
        return "total"
    if "btts" in p or "deux équipes" in p or "marquent" in p:
        return "btts"
    if "nul" in p:
        return "draw"
    return "h2h"


def normalize_pick(raw: Dict[str, Any], match: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    pari = str(raw.get("pari") or "").strip()
    if not pari:
        pari = candidates[0]["pari"] if candidates else f"Victoire {match['home']}"

    pari = pari.replace("Victoire X", f"Victoire {match['home']}")
    pari = pari.replace("Victoire Y", f"Victoire {match['away']}")

    chosen = None
    for c in candidates:
        if c["pari"].lower() == pari.lower():
            chosen = c
            break
    if chosen is None:
        p = pari.lower()
        for c in candidates:
            if ("btts" in p or "deux équipes" in p or "marquent" in p) and c["type"] == "btts":
                chosen = c; break
            if "plus de 2.5" in p and c["pari"].lower().startswith("plus de"):
                chosen = c; break
            if "moins de 2.5" in p and c["pari"].lower().startswith("moins de"):
                chosen = c; break
            if match["home"].lower() in p and c["pari"].lower() == f"victoire {match['home'].lower()}":
                chosen = c; break
            if match["away"].lower() in p and c["pari"].lower() == f"victoire {match['away'].lower()}":
                chosen = c; break
        if chosen:
            pari = chosen["pari"]

    odds = float(raw.get("cote_mini") or raw.get("odds_min") or (chosen or {}).get("odds") or 1.75)
    conf = int(float(raw.get("confiance") or raw.get("confidence") or 65))
    typ = (chosen or {}).get("type") or str(raw.get("market_type") or market_from_pari(pari))

    implied = 100 / odds if odds > 1 else 50
    if typ == "h2h":
        conf -= 3
    elif typ in ("total", "btts"):
        conf += 2
    if odds < 1.42:
        conf -= 7
    elif 1.55 <= odds <= 2.10:
        conf += 2
    elif odds > 2.80:
        conf -= 8
    seed = int(hashlib.sha1(f"{match['home']}-{match['away']}-{pari}".encode()).hexdigest(), 16)
    conf += (seed % 7) - 3
    conf = clamp(conf, 58, 91)

    stake = int(raw.get("mise_pct") or raw.get("stake_pct") or 2)
    if conf >= 84:
        stake = max(stake, 4)
    elif conf >= 76:
        stake = max(stake, 3)
    elif conf < 67:
        stake = min(stake, 2)
    stake = clamp(stake, 1, 5)

    value_score = round(conf + max(0, odds - 1.55) * 4 + (3 if typ in ("total", "btts") else 0), 2)
    return {
        "pari": pari,
        "market_type": typ,
        "conf": conf,
        "cote_mini": round(odds, 2),
        "mp": stake,
        "value_score": value_score,
        "resume": str(raw.get("resume") or raw.get("analyse") or raw.get("reason") or "Analyse non disponible.").strip()[:700],
        "risque": str(raw.get("risque") or raw.get("risk") or "Variance du football et information d'équipe incomplète.").strip()[:280],
    }


def parse_json_object(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("JSON introuvable")


async def short_agent(agent_id: str, match: Dict[str, Any], candidates: List[Dict[str, Any]], context: str) -> str:
    system = SYSTEM_BY_AGENT[agent_id]
    user = (
        f"Match: {match['home']} vs {match['away']}\n"
        f"Compétition: {match['competition']} | Coup d'envoi: {match['heure']} | Date: {match['date']}\n"
        f"Cotes disponibles: {json.dumps(candidates, ensure_ascii=False)}\n"
        f"Contexte: {context}\n"
        "Donne uniquement les signaux utiles pour choisir un marché de pari, pas de blabla."
    )
    return await groq(system, user, max_tokens=180, temperature=0.35)


async def final_pick(match: Dict[str, Any], candidates: List[Dict[str, Any]], reports: Dict[str, str], db: Dict[str, Any]) -> Dict[str, Any]:
    lessons = db.get("lessons", [])[-8:]
    history = summarize_history(db)
    system = (
        "Tu es un professeur expert en paris sportifs football. Tu dois choisir le MEILLEUR pari value parmi une liste de candidats réels. "
        "Tu n'as PAS le droit d'inventer un marché absent. Tu dois éviter de choisir automatiquement le vainqueur. "
        "Compare sérieusement victoire, nul, Over/Under 2.5 et BTTS si disponibles. "
        "Retourne uniquement du JSON valide."
    )
    user = f"""
MATCH: {match['home']} vs {match['away']}
COMPETITION: {match['competition']} | HEURE: {match['heure']} | DATE: {match['date']}
BOOKMAKER SOURCE: {match.get('bookmaker','')}
CANDIDATS AUTORISES (choisis seulement dans cette liste):
{json.dumps(candidates, ensure_ascii=False, indent=2)}

RAPPORTS AGENTS:
{json.dumps(reports, ensure_ascii=False, indent=2)}

HISTORIQUE APPRENTISSAGE:
{history}
LECONS RECENTES:
{json.dumps(lessons, ensure_ascii=False, indent=2)}

Réponds EXACTEMENT ce JSON:
{{
  "pari": "copie exacte d'un pari de la liste candidats",
  "market_type": "h2h|total|btts|draw",
  "confiance": 58-91,
  "mise_pct": 1-5,
  "cote_mini": nombre,
  "resume": "3 phrases courtes, logiques, intenses: pourquoi ce pari et pourquoi pas les autres",
  "risque": "risque principal en une phrase"
}}
Règles de calibration:
- 58-66 = correct mais fragile
- 67-74 = bon
- 75-82 = fort
- 83-91 = très rare, seulement si signaux très alignés
- Ne mets pas toujours 75 ou 82. Varie selon le match.
"""
    raw = await groq(system, user, max_tokens=460, temperature=0.25, json_mode=True)
    try:
        data = parse_json_object(raw)
    except Exception:
        log.warning("Bad final JSON: %s", raw[:500])
        data = {"pari": candidates[0]["pari"] if candidates else f"Victoire {match['home']}", "confiance": 64, "mise_pct": 2, "cote_mini": (candidates[0]["odds"] if candidates else 1.75), "resume": raw[:350], "risque": "Parsing incomplet."}
    return normalize_pick(data, match, candidates)


def summarize_history(db: Dict[str, Any]) -> str:
    picks = [p for s in db.get("scans", {}).values() for p in s.get("picks", [])]
    decided = [p for p in picks if p.get("result") in ("win", "loss")]
    if not decided:
        return "Pas encore assez d'historique."
    out = []
    for typ in ["h2h", "total", "btts", "draw"]:
        rows = [p for p in decided if p.get("market_type") == typ]
        if rows:
            wins = sum(1 for p in rows if p.get("result") == "win")
            out.append(f"{typ}: {wins}/{len(rows)} = {round(wins/len(rows)*100)}%")
    return " | ".join(out) if out else "Historique insuffisant."


async def analyze_match(match: Dict[str, Any], db: Dict[str, Any], progress_cb) -> Optional[Dict[str, Any]]:
    candidates = build_candidates(match)
    if not candidates:
        return None
    context = await groq(
        "Tu es analyste football. Contexte factuel, sobre, sans inventer d'absence non vérifiée.",
        f"Donne le contexte court pour {match['home']} vs {match['away']} ({match['competition']}, {match['heure']}). 100 mots max.",
        max_tokens=180,
        temperature=0.25,
    )
    reports: Dict[str, str] = {}
    core_agents = ["tact", "stat", "phys", "scout", "market", "psy", "tempo", "risk", "judge"]
    total = len(core_agents) + 1
    done = 0
    for aid in core_agents:
        await progress_cb(aid, done, total)
        reports[aid] = await short_agent(aid, match, candidates, context)
        done += 1
        await progress_cb(aid, done, total)
    await progress_cb("prof", done, total)
    verdict = await final_pick(match, candidates, reports, db)
    done += 1
    await progress_cb("prof", done, total)
    return {"match": match, "candidates": candidates, "reports": reports, "verdict": verdict}


def prog_bar(pct: int, size: int = 10) -> str:
    filled = round(size * pct / 100)
    return "█" * filled + "░" * (size - filled)


def progress_text(index: int, total: int, match: Dict[str, Any], states: Dict[str, str], pct: int) -> str:
    lines = [
        f"🔬 <b>Analyse {index + 1}/{total}</b> — {esc(match['home'])} vs {esc(match['away'])}",
        f"🏆 {esc(match['competition'])} · ⏰ {esc(match['heure'])}",
        f"<code>{prog_bar(pct)} {pct}%</code>",
        "",
    ]
    for aid, name, emoji in AGENTS:
        state = states.get(aid, "wait")
        icon = "✅" if state == "done" else "⚡" if state == "run" else "⏳"
        lines.append(f"{emoji} {esc(name)} {icon}")
    return "\n".join(lines)


def pick_message(rank: int, pick: Dict[str, Any]) -> str:
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][rank - 1] if rank <= 5 else f"#{rank}"
    stake = round(BANKROLL * pick.get("mp", 2) / 100, 2)
    odds = float(pick.get("cote_mini", 1.75))
    ret = round(stake * odds, 2)
    profit = round(ret - stake, 2)
    conf = int(pick.get("conf", 65))
    label = "🔥 ELITE" if conf >= 84 else "🔥 FORT" if conf >= 76 else "✅ BON" if conf >= 68 else "👍 CORRECT"
    lines = [
        f"{medal} <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>",
        f"🏆 {esc(pick.get('comp',''))} · ⏰ {esc(pick.get('heure',''))}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>PARI : {esc(pick['pari'])}</b>",
        f"🧩 Marché : <b>{esc(pick.get('market_type',''))}</b>",
        f"📊 Confiance : <code>{prog_bar(conf)}</code> <b>{conf}%</b> {label}",
        f"💎 Score value : <b>{esc(pick.get('value_score', conf))}</b>",
        f"⚡ Cote mini : <b>{odds}</b>",
        f"💰 Mise : <b>{stake}€</b> ({pick.get('mp',2)}% de {BANKROLL}€)",
        f"🎁 Si gagne : <b>{ret}€</b> · Profit <b>+{profit}€</b>",
        "",
        f"💡 <b>Pourquoi :</b>\n{esc(pick.get('resume',''))}",
        "",
        f"⚠️ <b>Risque :</b> {esc(pick.get('risque',''))}",
    ]
    return "\n".join(lines)


async def run_scan(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    db = db_load()
    target = target_day()
    bot = context.bot
    if not force and target["key"] in db.get("scans", {}) and db["scans"][target["key"]].get("picks"):
        await bot.send_message(CHAT_ID, f"💾 Scan déjà fait pour {esc(target['label'])}.\nUtilise /resultats ou /scan force.", parse_mode=ParseMode.HTML)
        return

    header = await bot.send_message(
        CHAT_ID,
        f"⚽ <b>ORACLE — {esc(target['mode'])}</b>\n☀️ {esc(target['label'])}\n\n🔍 Recherche matchs + marchés réels...",
        parse_mode=ParseMode.HTML,
    )
    try:
        matches = await fetch_matches(target["iso_date"], target["label"])
    except Exception as e:
        await header.edit_text(f"❌ Erreur données : {esc(e)}", parse_mode=ParseMode.HTML)
        return
    if not matches:
        await header.edit_text(f"❌ Aucun match avec cotes trouvé pour {esc(target['label'])}.", parse_mode=ParseMode.HTML)
        return

    await header.edit_text(
        f"⚽ <b>ORACLE — {esc(target['label'])}</b>\n✅ {len(matches)} matchs réels avec marchés\n🔬 Analyse experte en cours...",
        parse_mode=ParseMode.HTML,
    )
    results: List[Dict[str, Any]] = []
    for i, match in enumerate(matches[:10]):
        states = {aid: "wait" for aid, _, _ in AGENTS}
        pmsg = await bot.send_message(CHAT_ID, progress_text(i, min(len(matches), 10), match, states, 0), parse_mode=ParseMode.HTML)

        async def progress(aid: str, done: int, total: int) -> None:
            states[aid] = "run" if states.get(aid) != "done" else "done"
            if done > 0:
                states[aid] = "done"
            pct = clamp(round(done / total * 100), 0, 100)
            try:
                await pmsg.edit_text(progress_text(i, min(len(matches), 10), match, states, pct), parse_mode=ParseMode.HTML)
            except Exception:
                pass

        try:
            res = await analyze_match(match, db, progress)
            if res:
                results.append(res)
                v = res["verdict"]
                await pmsg.edit_text(
                    f"✅ <b>{esc(match['home'])} vs {esc(match['away'])}</b>\n<code>{prog_bar(100)} 100%</code>\n\n🎯 {esc(v['pari'])}\n📊 {v['conf']}% · score {v['value_score']}",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as e:
            log.exception("Analyze failed")
            await pmsg.edit_text(f"❌ {esc(match['home'])} vs {esc(match['away'])}: {esc(e)}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)

    if not results:
        await bot.send_message(CHAT_ID, "❌ Aucune analyse exploitable.")
        return

    results.sort(key=lambda r: (r["verdict"].get("conf", 0), r["verdict"].get("value_score", 0)), reverse=True)
    top = results[:5]
    picks: List[Dict[str, Any]] = []
    for r in top:
        m, v = r["match"], r["verdict"]
        picks.append({
            "home": m["home"], "away": m["away"], "comp": m["competition"], "heure": m["heure"],
            "bookmaker": m.get("bookmaker", ""), "pari": v["pari"], "market_type": v["market_type"],
            "conf": v["conf"], "value_score": v["value_score"], "cote_mini": v["cote_mini"],
            "mp": v["mp"], "resume": v["resume"], "risque": v["risque"], "result": None,
        })
    db.setdefault("scans", {})[target["key"]] = {
        "date_key": target["key"], "date_label": target["label"], "mode": target["mode"],
        "scanned_at": target["scanned_at"], "picks": picks,
    }
    db_save(db)

    await bot.send_message(CHAT_ID, f"🏆 <b>TOP {len(picks)} — {esc(target['label'])}</b>\nTrié par confiance puis value score.", parse_mode=ParseMode.HTML)
    for idx, pick in enumerate(picks):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"res:{target['key']}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{target['key']}:{idx}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{target['key']}:{idx}:cancel"),
        ]])
        await bot.send_message(CHAT_ID, pick_message(idx + 1, pick), parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.3)
    await bot.send_message(CHAT_ID, "✅ Scan terminé. /resultats pour saisir les WIN/LOSS plus tard.")


async def learn_from_pick(pick: Dict[str, Any], db: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE) -> None:
    result = pick.get("result")
    lesson = {
        "ts": datetime.now(PARIS_TZ).isoformat(),
        "market_type": pick.get("market_type"),
        "result": result,
        "text": f"{pick.get('market_type')} sur {pick.get('home')} vs {pick.get('away')} => {result}. Pari: {pick.get('pari')} confiance {pick.get('conf')}%."
    }
    db.setdefault("lessons", []).append(lesson)
    db["lessons"] = db["lessons"][-80:]
    db_save(db)
    await context.bot.send_message(CHAT_ID, f"🧬 Leçon enregistrée : {esc(lesson['text'])}", parse_mode=ParseMode.HTML)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner maintenant", callback_data="launch_scan")]])
    await update.message.reply_text(
        "⚽ <b>ORACLE FOOTBALL V2</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Cotes réelles via Odds API\n✅ 10 agents Groq\n✅ Marchés variés: victoire, nul, Over/Under 2.5, BTTS\n✅ Classement par confiance + value\n\n"
        "/scan — lancer\n/scan force — refaire le scan\n/resultats — saisir WIN/LOSS\n/stats — stats",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    await run_scan(context, force=bool(context.args and context.args[0].lower() == "force"))


async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    db = db_load()
    pending = []
    for dk, scan in db.get("scans", {}).items():
        for idx, pick in enumerate(scan.get("picks", [])):
            if pick.get("result") is None:
                pending.append((dk, scan.get("date_label", dk), idx, pick))
    if not pending:
        await update.message.reply_text("✅ Aucun résultat en attente.")
        return
    await update.message.reply_text(f"⏳ {len(pending)} paris en attente.")
    for dk, label, idx, pick in pending[:12]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel"),
        ]])
        await update.message.reply_text(
            f"📅 {esc(label)}\n⚽ <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>\n🎯 {esc(pick['pari'])} · {pick['conf']}%",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    db = db_load()
    picks = [p for scan in db.get("scans", {}).values() for p in scan.get("picks", [])]
    decided = [p for p in picks if p.get("result") in ("win", "loss")]
    wins = [p for p in decided if p.get("result") == "win"]
    wr = round(len(wins) / len(decided) * 100, 1) if decided else 0
    by_type = summarize_history(db)
    await update.message.reply_text(
        f"📊 <b>STATS ORACLE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"Paris décidés: <b>{len(decided)}</b>\nWins: <b>{len(wins)}</b>\nWinrate: <b>{wr}%</b>\n"
        f"Marchés: {esc(by_type)}\nLeçons: <b>{len(db.get('lessons', []))}</b>",
        parse_mode=ParseMode.HTML,
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if q.message.chat_id != CHAT_ID:
        return
    if q.data == "launch_scan":
        await run_scan(context, force=False)
        return
    if not q.data.startswith("res:"):
        return
    _, dk, idx_s, result = q.data.split(":")
    idx = int(idx_s)
    db = db_load()
    scan = db.get("scans", {}).get(dk)
    if not scan or idx >= len(scan.get("picks", [])):
        await q.edit_message_text("Résultat introuvable.")
        return
    pick = scan["picks"][idx]
    if result == "cancel":
        pick["result"] = "cancelled"
        db_save(db)
        await q.edit_message_text(q.message.text_html + "\n\n🚫 Annulé.", parse_mode=ParseMode.HTML)
        return
    pick["result"] = result
    db_save(db)
    await q.edit_message_text(q.message.text_html + f"\n\n{'✅' if result == 'win' else '❌'} <b>{result.upper()} enregistré</b>", parse_mode=ParseMode.HTML)
    await learn_from_pick(pick, db, context)


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_scan(context, force=False)


def main() -> None:
    if not TOKEN:
        raise SystemExit("TELEGRAM_TOKEN manquant")
    if not CHAT_ID:
        raise SystemExit("CHAT_ID manquant")
    if not GROQ_KEYS:
        raise SystemExit("GROQ_KEYS manquante")
    if not ODDS_API_KEY:
        raise SystemExit("ODDSPAPI_KEY ou ODDS_API_KEY manquante")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(callback))

    app.job_queue.run_daily(daily_job, time=datetime.strptime(f"{SCAN_HOUR:02d}:00", "%H:%M").time(), days=(0,1,2,3,4,5,6), chat_id=CHAT_ID)
    log.info("Oracle Bot V2 démarré — scan auto à %sh Paris", SCAN_HOUR)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
