# Oracle Bot V4.5 - Multi-Agent Council
# Stable entrypoint remains main.py. This module wraps the stable V4.3 engine
# and replaces selection/UX with an agent-council pipeline.

from typing import Any, Dict, List, Tuple

import oracle_bot_v43 as bot

VERSION = "V4.5"
VERSION_NAME = "ORACLE FOOTBALL V4.5 - MULTI-AGENT COUNCIL"


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _grade(conf: float, danger: float, ev: float, decision: str) -> str:
    if decision == "ACCEPT" and conf >= 68 and danger <= 45 and ev >= 1.5:
        return "A"
    if decision == "ACCEPT":
        return "B+"
    if decision == "WATCHLIST":
        return "B-"
    return "C"


def _agent_line(icon: str, name: str, verdict: str, note: str) -> str:
    return f"{icon} <b>{name}</b> : {verdict} - {bot.e(note)}"


def _memory_lookup(db: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    prof = db.get("learning") or bot.learning(db)
    market = prof.get("by_market", {}).get(p.get("market_type"), {})
    odds_bucket = bot.ob(_num(p.get("odds"), 2.0))
    odds = prof.get("by_odds", {}).get(odds_bucket, {})
    league = prof.get("by_league", {}).get(bot.lb(p.get("competition", "")), {})
    return {"samples": prof.get("samples", 0), "market": market, "odds": odds, "league": league, "odds_bucket": odds_bucket}


def council(p: Dict[str, Any], db: Dict[str, Any]) -> Dict[str, Any]:
    ev = _num(p.get("ev_pct"))
    value = _num(p.get("value_score"))
    conf = _num(p.get("confidence"))
    danger = _num(p.get("danger"))
    edge = _num(p.get("edge_pct"))
    odds = _num(p.get("odds"), 2.0)
    market_type = str(p.get("market_type", ""))
    lg = bot.lb(p.get("competition", ""))
    mem = _memory_lookup(db, p)
    votes: Dict[str, Dict[str, Any]] = {}

    market_score = 0
    if edge >= 2.5:
        market_score += 2
    elif edge >= 1.0:
        market_score += 1
    else:
        market_score -= 1
    if 1.55 <= odds <= 2.35:
        market_score += 1
    if odds >= 3.2:
        market_score -= 2
    votes["market"] = {"vote": "ACCEPT" if market_score >= 2 else "WATCHLIST" if market_score >= 0 else "REJECT", "score": market_score, "note": f"edge {edge}% et cote {odds}"}

    value_score = 0
    if ev >= 2.0:
        value_score += 3
    elif ev >= 0.5:
        value_score += 2
    elif ev >= 0:
        value_score += 1
    else:
        value_score -= 3
    if value >= 4:
        value_score += 1
    elif value < 0:
        value_score -= 1
    votes["value"] = {"vote": "ACCEPT" if value_score >= 3 else "WATCHLIST" if value_score >= 0 else "REJECT", "score": value_score, "note": f"EV {ev}% / value {value}"}

    risk_score = 0
    if danger <= 38:
        risk_score += 2
    elif danger <= 55:
        risk_score += 1
    else:
        risk_score -= 2
    if market_type == "draw":
        risk_score -= 2
    if market_type == "h2h":
        risk_score -= 1
    if lg == "volatile":
        risk_score -= 2
    if odds >= 2.8:
        risk_score -= 1
    votes["risk"] = {"vote": "ACCEPT" if risk_score >= 2 else "WATCHLIST" if risk_score >= 0 else "REJECT", "score": risk_score, "note": f"danger {danger}% / ligue {lg}"}

    tempo_score = 0
    if market_type in ("btts", "total"):
        tempo_score += 2
    elif market_type == "h2h":
        tempo_score -= 1
    if conf >= 66:
        tempo_score += 1
    votes["tempo"] = {"vote": "ACCEPT" if tempo_score >= 2 else "WATCHLIST" if tempo_score >= 0 else "REJECT", "score": tempo_score, "note": "marché buts favorisé" if market_type in ("btts", "total") else "H2H moins prioritaire"}

    memory_score = 0
    samples = int(mem.get("samples", 0) or 0)
    mem_notes = []
    if samples < 20:
        mem_notes.append(f"{samples} samples: mémoire prudente")
    else:
        for label, st in [("marché", mem["market"]), ("cote", mem["odds"]), ("ligue", mem["league"])]:
            n = int(st.get("n", 0) or 0)
            roi = _num(st.get("roi"))
            if n >= 8:
                if roi > 8:
                    memory_score += 1
                elif roi < -8:
                    memory_score -= 1
                mem_notes.append(f"{label} ROI {roi}%")
    votes["memory"] = {"vote": "ACCEPT" if memory_score >= 2 else "WATCHLIST" if memory_score >= -1 else "REJECT", "score": memory_score, "note": "; ".join(mem_notes) if mem_notes else "mémoire neutre"}

    contra_score = 0
    reasons = []
    if ev < 0:
        contra_score -= 3
        reasons.append("EV négative")
    if market_type == "h2h" and edge < 2.0:
        contra_score -= 1
        reasons.append("H2H edge faible")
    if danger > 55:
        contra_score -= 2
        reasons.append("danger élevé")
    if odds >= 3.2:
        contra_score -= 2
        reasons.append("cote très haute")
    if not reasons:
        contra_score += 1
        reasons.append("pas de contradiction forte")
    votes["contradiction"] = {"vote": "ACCEPT" if contra_score >= 1 else "WATCHLIST" if contra_score >= -2 else "REJECT", "score": contra_score, "note": ", ".join(reasons)}

    total_score = sum(v["score"] for v in votes.values())
    reject_count = sum(1 for v in votes.values() if v["vote"] == "REJECT")
    accept_count = sum(1 for v in votes.values() if v["vote"] == "ACCEPT")

    if ev < 0:
        decision = "WATCHLIST" if conf >= 64 and danger <= 42 and reject_count <= 2 else "REJECT"
        stake_pct = 0
    elif total_score >= 6 and accept_count >= 3 and reject_count == 0 and conf >= 60 and danger <= 58:
        decision = "ACCEPT"
        stake_pct = 1 if ev < 1.5 else min(int(p.get("stake_pct", 1) or 1), 2)
    elif total_score >= 1 and reject_count <= 2 and conf >= 56:
        decision = "WATCHLIST"
        stake_pct = 0
    else:
        decision = "REJECT"
        stake_pct = 0

    return {"decision": decision, "council_score": round(total_score, 2), "accept_count": accept_count, "reject_count": reject_count, "grade": _grade(conf, danger, ev, decision), "votes": votes, "stake_pct": stake_pct}


def enrich_with_council(rows: List[Dict[str, Any]], db: Dict[str, Any]) -> List[Dict[str, Any]]:
    enriched = []
    for p in rows:
        data = council(p, db)
        q = dict(p)
        q["decision"] = data["decision"]
        q["council_score"] = data["council_score"]
        q["agent_votes"] = data["votes"]
        q["agent_accepts"] = data["accept_count"]
        q["agent_rejects"] = data["reject_count"]
        q["quality"] = data["grade"]
        q["stake_pct"] = data["stake_pct"]
        enriched.append(q)
    return enriched


def select_council_picks(rows: List[Dict[str, Any]], top_limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = sorted(rows, key=lambda p: (1 if p.get("decision") == "ACCEPT" else 0, p.get("council_score", 0), p.get("ev_pct", -99), p.get("value_score", -99) - 0.2 * p.get("danger", 50), p.get("confidence", 0)), reverse=True)
    accepts, watch, rejects = [], [], []
    seen_top = set()
    h2h_top = 0
    for p in rows:
        if p.get("decision") == "ACCEPT":
            if p.get("match_id") in seen_top:
                continue
            if p.get("market_type") == "h2h" and h2h_top >= max(1, bot.MAX_H2H_TOP):
                watch.append(p)
                continue
            accepts.append(p)
            seen_top.add(p.get("match_id"))
            if p.get("market_type") == "h2h":
                h2h_top += 1
            if len(accepts) >= top_limit:
                break
    for p in rows:
        if p.get("match_id") in seen_top:
            continue
        if p.get("decision") == "WATCHLIST":
            watch.append(p)
            seen_top.add(p.get("match_id"))
        elif p.get("decision") == "REJECT":
            rejects.append(p)
    return accepts[:top_limit], watch[: min(6, top_limit + 2)], rejects


def _agent_text(p: Dict[str, Any]) -> str:
    votes = p.get("agent_votes", {})
    labels = [("📈", "Market", "market"), ("💎", "Value", "value"), ("🛡", "Risk", "risk"), ("⚽", "Tempo", "tempo"), ("🧠", "Memory", "memory"), ("⚔️", "Contra", "contradiction")]
    return "\n".join(_agent_line(icon, name, votes.get(key, {}).get("vote", "?"), votes.get(key, {}).get("note", "")) for icon, name, key in labels)


def council_card(rank: int, p: Dict[str, Any], section: str) -> str:
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
    marker = medals[rank - 1] if rank <= len(medals) else str(rank)
    stake = round(bot.BANKROLL * (p.get("stake_pct", 0) or 0) / 100, 2)
    ret = round(stake * _num(p.get("odds"), 1.0), 2)
    profit = round(ret - stake, 2)
    stake_line = "0 EUR (observation)" if stake <= 0 else f"{stake} EUR · retour {ret} EUR · profit +{profit} EUR"
    return (
        f"{marker} <b>{bot.e(p['home'])} vs {bot.e(p['away'])}</b>\n"
        f"🏆 {bot.e(p['competition'])} · ⏰ {bot.e(p['heure'])} · Qualité {p.get('quality','B-')}\n"
        f"🧬 Oracle V4.5 · <b>{section}</b> · Décision <b>{p.get('decision','WATCHLIST')}</b>\n\n"
        f"🎯 <b>{bot.e(p['pari'])}</b>\n"
        f"🧩 {bot.e(p['market_type'])} · ⚡ cote {p['odds']}\n"
        f"📊 Conf <b>{p['confidence']}%</b> · ⚠️ Danger <b>{p['danger']}%</b>\n"
        f"💎 Value {p['value_score']} · EV <b>{p['ev_pct']}%</b> · ML {p.get('learning_adj', 0)}\n"
        f"🗳 Council score {p.get('council_score', 0)} · ✅ {p.get('agent_accepts', 0)} / ❌ {p.get('agent_rejects', 0)}\n"
        f"💰 Mise : {stake_line}\n\n"
        f"🤖 <b>Conseil des agents</b>\n{_agent_text(p)}\n\n"
        f"📝 Enregistré. Résultat auto demain."
    )


def stats_v45_text(db: Dict[str, Any]) -> str:
    base = bot.stats_text(db) if hasattr(bot, "stats_text") else ""
    rows = bot.decided(db)
    by_decision: Dict[str, Dict[str, float]] = {}
    for p in rows:
        k = p.get("decision", "unknown")
        by_decision.setdefault(k, {"n": 0, "w": 0, "profit": 0.0})
        by_decision[k]["n"] += 1
        by_decision[k]["w"] += 1 if p.get("result") == "win" else 0
        by_decision[k]["profit"] += bot.unit(p)
    lines = ["\n<b>Décisions Council V4.5</b>"]
    if not by_decision:
        lines.append("• pas encore assez de résultats par décision")
    else:
        for k, v in by_decision.items():
            wr = round(v["w"] / v["n"] * 100, 1) if v["n"] else 0
            roi = round(v["profit"] / v["n"] * 100, 1) if v["n"] else 0
            lines.append(f"• {bot.e(k)}: {int(v['w'])}/{int(v['n'])} · WR {wr}% · ROI {roi}%")
    return (base + "\n" + "\n".join(lines)).strip()


async def run_scan_v45(ctx, force: bool = False) -> None:
    await bot.auto_settle(ctx, False)
    db = bot.load_db()
    db["learning"] = bot.learning(db)
    bot.save_db(db)
    d = bot.day_target()
    if not force and db["scans"].get(d["key"], {}).get("picks"):
        await ctx.bot.send_message(bot.CHAT_ID, "Scan déjà fait. /scan force pour refaire.")
        return
    msg = await ctx.bot.send_message(bot.CHAT_ID, f"🔎 <b>Oracle V4.5 — Multi-Agent Council</b>\n📅 {d['label']} · Mode {bot.MODE}\n🧠 ML samples: {db['learning'].get('samples', 0)}\n🤖 Agents: Market · Value · Risk · Tempo · Memory · Contra · Judge\nRègle forte: EV négative = jamais TOP PICK.\nRecherche...", parse_mode=bot.ParseMode.HTML)
    matches = await bot.odds_matches(d["key"])
    if not matches:
        await msg.edit_text("Aucun match avec cotes trouvé.")
        return
    selected = bot.pool(matches, db)[: bot.MAX_ANALYZED]
    await msg.edit_text(f"✅ {len(matches)} matchs avec cotes\n🧪 {len(selected)} marchés filtrés\n🤖 Conseil des agents en cours...\n🧬 Version: <b>V4.5</b>", parse_mode=bot.ParseMode.HTML)
    rows = []
    for it in selected:
        m, c = it["match"], it["candidate"]
        sc = bot.score(m, c, it["prefilter_score"], db)
        rows.append({"match_id": m["id"], "date_key": d["key"], "home": m["home"], "away": m["away"], "competition": m["competition"], "heure": m["heure"], "source": m["source"], "bookmaker": m["bookmaker"], "pari": c["pari"], "market_type": c["type"], "odds": round(c["odds"], 2), "result": None, **sc})
    enriched = enrich_with_council(rows, db)
    top_picks, watchlist, rejected = select_council_picks(enriched, bot.TOP_PICKS)
    displayed = top_picks + watchlist
    db["scans"][d["key"]] = {"date_key": d["key"], "date_label": d["label"], "scanned_at": d["at"], "mode": bot.MODE, "version": VERSION, "ml_samples": db["learning"].get("samples", 0), "picks": displayed, "rejected_count": len(rejected)}
    bot.save_db(db)
    await msg.edit_text(f"🧬 <b>Oracle V4.5 — Multi-Agent Council</b>\n📅 {bot.e(d['label'])}\n🏆 TOP PICKS: <b>{len(top_picks)}</b>\n👀 WATCHLIST: <b>{len(watchlist)}</b>\n🚫 Rejetés: <b>{len(rejected)}</b>\n✅ Tout ce qui est affiché est enregistré pour auto-check demain à {bot.SETTLE_HOUR}h.", parse_mode=bot.ParseMode.HTML)
    if top_picks:
        await ctx.bot.send_message(bot.CHAT_ID, "🏆 <b>TOP PICKS — acceptés par le Council</b>", parse_mode=bot.ParseMode.HTML)
        for i, p in enumerate(top_picks, 1):
            idx = displayed.index(p)
            kb = bot.InlineKeyboardMarkup([[bot.InlineKeyboardButton("✅ WIN", callback_data=f"res:{d['key']}:{idx}:win"), bot.InlineKeyboardButton("❌ LOSS", callback_data=f"res:{d['key']}:{idx}:loss"), bot.InlineKeyboardButton("🚫 Annuler", callback_data=f"res:{d['key']}:{idx}:cancel")]])
            await ctx.bot.send_message(bot.CHAT_ID, council_card(i, p, "TOP PICK"), parse_mode=bot.ParseMode.HTML, reply_markup=kb)
    else:
        await ctx.bot.send_message(bot.CHAT_ID, "🏆 <b>TOP PICKS</b>\nAucun pick élite aujourd’hui : le Council refuse de forcer une value négative.", parse_mode=bot.ParseMode.HTML)
    if watchlist:
        await ctx.bot.send_message(bot.CHAT_ID, "👀 <b>WATCHLIST — surveillés, pas joués fort</b>", parse_mode=bot.ParseMode.HTML)
        for i, p in enumerate(watchlist, 1):
            idx = displayed.index(p)
            kb = bot.InlineKeyboardMarkup([[bot.InlineKeyboardButton("✅ WIN", callback_data=f"res:{d['key']}:{idx}:win"), bot.InlineKeyboardButton("❌ LOSS", callback_data=f"res:{d['key']}:{idx}:loss"), bot.InlineKeyboardButton("🚫 Annuler", callback_data=f"res:{d['key']}:{idx}:cancel")]])
            await ctx.bot.send_message(bot.CHAT_ID, council_card(i, p, "WATCHLIST"), parse_mode=bot.ParseMode.HTML, reply_markup=kb)
    await ctx.bot.send_message(bot.CHAT_ID, "✅ Scan V4.5 terminé. Les résultats de demain recalibreront la mémoire du Council.")


async def start_v45(update, context):
    if update.effective_chat.id != bot.CHAT_ID:
        return
    await update.message.reply_text("⚽ <b>ORACLE FOOTBALL V4.5</b>\n━━━━━━━━━━━━━━\n🤖 Multi-Agent Council\n📈 Market Agent\n💎 Value Agent\n🛡 Risk Agent\n⚽ Tempo Agent\n🧠 Memory Agent\n⚔️ Contradiction Agent\n⚖️ Final Judge\n\n✅ TOP PICKS / WATCHLIST / REJECT\n✅ EV négative interdite en TOP\n✅ Auto-settle + apprentissage quotidien\n✅ Railway reste sur <code>python main.py</code>\n\n/scan force\n/settle\n/stats\n/chart\n/resultats", parse_mode=bot.ParseMode.HTML)


async def scan_cmd_v45(update, context):
    if update.effective_chat.id == bot.CHAT_ID:
        await run_scan_v45(context, bool(context.args and context.args[0].lower() == "force"))


async def stats_cmd_v45(update, context):
    if update.effective_chat.id == bot.CHAT_ID:
        await update.message.reply_text(stats_v45_text(bot.load_db()), parse_mode=bot.ParseMode.HTML)


async def job_scan_v45(context):
    await run_scan_v45(context, False)


def main():
    bot.valid_env()
    app = bot.Application.builder().token(bot.TOKEN).build()
    app.add_handler(bot.CommandHandler("start", start_v45))
    app.add_handler(bot.CommandHandler("scan", scan_cmd_v45))
    app.add_handler(bot.CommandHandler("settle", bot.settle_cmd))
    app.add_handler(bot.CommandHandler("stats", stats_cmd_v45))
    app.add_handler(bot.CommandHandler("learn", bot.learn_cmd))
    app.add_handler(bot.CommandHandler("chart", bot.chart_cmd))
    app.add_handler(bot.CommandHandler("resultats", bot.resultats))
    app.add_handler(bot.CallbackQueryHandler(bot.cb))
    app.job_queue.run_daily(bot.job_settle, time=bot.time(hour=bot.SETTLE_HOUR, minute=0, tzinfo=bot.TZ), days=(0,1,2,3,4,5,6), chat_id=bot.CHAT_ID)
    app.job_queue.run_daily(job_scan_v45, time=bot.time(hour=bot.SCAN_HOUR, minute=0, tzinfo=bot.TZ), days=(0,1,2,3,4,5,6), chat_id=bot.CHAT_ID)
    bot.log.info("Oracle Bot V4.5 Multi-Agent Council started mode=%s", bot.MODE)
    app.run_polling(allowed_updates=bot.Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
