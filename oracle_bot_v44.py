# Oracle Bot V4.4
# Patch léger au-dessus de V4.3 : corrige le Top qui sort parfois 1 seul pick.
# Cause : MAX_H2H_TOP=1 bloque les H2H, et si peu de BTTS/total sont disponibles,
# la sélection ne remplit pas TOP_PICKS.

import oracle_bot_v43 as bot

VERSION = "ORACLE FOOTBALL V4.4"


def pick_cards_v44(rows):
    """Sélection plus intelligente :
    1) préfère BTTS / total,
    2) respecte MAX_H2H_TOP au premier passage,
    3) remplit ensuite le Top avec les meilleurs picks restants si nécessaire.
    """
    rows = sorted(
        rows,
        key=lambda p: (p.get("value_score", 0) - 0.25 * p.get("danger", 50), p.get("confidence", 0)),
        reverse=True,
    )

    selected = []
    seen_matches = set()
    h2h_count = 0

    preferred = [p for p in rows if p.get("market_type") in ("total", "btts")]
    secondary = [p for p in rows if p.get("market_type") in ("draw", "h2h")]

    # Passage 1 : stratégie stricte.
    for p in preferred + secondary:
        if p.get("match_id") in seen_matches:
            continue
        if p.get("market_type") == "h2h" and h2h_count >= bot.MAX_H2H_TOP:
            continue
        if len(selected) >= 3 and (p.get("confidence", 0) < bot.CFG[0] or p.get("value_score", -999) < bot.CFG[1]):
            continue
        selected.append(p)
        seen_matches.add(p.get("match_id"))
        if p.get("market_type") == "h2h":
            h2h_count += 1
        if len(selected) >= bot.TOP_PICKS:
            return selected[: bot.TOP_PICKS]

    # Passage 2 : fallback. On remplit le Top, mais uniquement avec des picks décents.
    # Cela évite le bug TOP 1 quand les marchés alternatifs manquent.
    for p in rows:
        if p.get("match_id") in seen_matches:
            continue
        if p.get("confidence", 0) < 56:
            continue
        if p.get("danger", 100) > 70:
            continue
        selected.append(p)
        seen_matches.add(p.get("match_id"))
        if len(selected) >= bot.TOP_PICKS:
            break

    return selected[: bot.TOP_PICKS]


async def start_v44(update, context):
    if update.effective_chat.id != bot.CHAT_ID:
        return
    await update.message.reply_text(
        "⚽ <b>ORACLE FOOTBALL V4.4</b>\n"
        "━━━━━━━━━━━━━━\n"
        "✅ Interface propre\n"
        "✅ Picks enregistrés\n"
        "✅ Auto-settle le lendemain\n"
        "✅ Stats + graphique\n"
        "✅ Correction Top incomplet\n"
        "✅ Version visible à chaque scan\n\n"
        "/scan force\n/settle\n/stats\n/chart\n/resultats",
        parse_mode=bot.ParseMode.HTML,
    )


async def run_scan_v44(ctx, force=False):
    # On réutilise la logique V4.3, mais avec la sélection corrigée.
    await bot.auto_settle(ctx, False)
    db = bot.load_db()
    db["learning"] = bot.learning(db)
    bot.save_db(db)
    d = bot.day_target()

    if not force and db["scans"].get(d["key"], {}).get("picks"):
        await ctx.bot.send_message(bot.CHAT_ID, "Scan déjà fait. /scan force pour refaire.")
        return

    msg = await ctx.bot.send_message(
        bot.CHAT_ID,
        f"🔎 <b>Oracle V4.4</b>\n"
        f"📅 {d['label']} · Mode {bot.MODE}\n"
        f"🧠 ML samples: {db['learning'].get('samples', 0)}\n"
        f"⚙️ Top visé: {bot.TOP_PICKS} · H2H strict: {bot.MAX_H2H_TOP}\n"
        "Recherche...",
        parse_mode=bot.ParseMode.HTML,
    )

    matches = await bot.odds_matches(d["key"])
    if not matches:
        await msg.edit_text("Aucun match avec cotes trouvé.")
        return

    selected = bot.pool(matches, db)[: bot.MAX_ANALYZED]
    await msg.edit_text(
        f"✅ {len(matches)} matchs avec cotes\n"
        f"🧪 {len(selected)} marchés filtrés\n"
        f"🧠 ML samples: {db['learning'].get('samples', 0)}\n"
        "Tri final V4.4...",
        parse_mode=bot.ParseMode.HTML,
    )

    rows = []
    for it in selected:
        m, c = it["match"], it["candidate"]
        sc = bot.score(m, c, it["prefilter_score"], db)
        rows.append(
            {
                "match_id": m["id"],
                "date_key": d["key"],
                "home": m["home"],
                "away": m["away"],
                "competition": m["competition"],
                "heure": m["heure"],
                "source": m["source"],
                "bookmaker": m["bookmaker"],
                "pari": c["pari"],
                "market_type": c["type"],
                "odds": round(c["odds"], 2),
                "result": None,
                **sc,
            }
        )

    picks = pick_cards_v44(rows)
    db["scans"][d["key"]] = {
        "date_key": d["key"],
        "date_label": d["label"],
        "scanned_at": d["at"],
        "mode": bot.MODE,
        "version": "V4.4",
        "ml_samples": db["learning"].get("samples", 0),
        "picks": picks,
    }
    bot.save_db(db)

    await msg.edit_text(
        f"🏆 <b>TOP {len(picks)} — {bot.e(d['label'])}</b>\n"
        f"🧬 Version: <b>V4.4</b>\n"
        f"✅ Picks enregistrés · Auto-check demain à {bot.SETTLE_HOUR}h\n"
        f"ℹ️ Si les marchés BTTS/total manquent, V4.4 complète le Top avec les meilleurs picks restants.",
        parse_mode=bot.ParseMode.HTML,
    )

    for i, p in enumerate(picks, 1):
        kb = bot.InlineKeyboardMarkup(
            [[
                bot.InlineKeyboardButton("✅ WIN", callback_data=f"res:{d['key']}:{i-1}:win"),
                bot.InlineKeyboardButton("❌ LOSS", callback_data=f"res:{d['key']}:{i-1}:loss"),
                bot.InlineKeyboardButton("🚫 Annuler", callback_data=f"res:{d['key']}:{i-1}:cancel"),
            ]]
        )
        await ctx.bot.send_message(bot.CHAT_ID, bot.card(i, p), parse_mode=bot.ParseMode.HTML, reply_markup=kb)

    await ctx.bot.send_message(bot.CHAT_ID, "✅ Scan V4.4 terminé. /stats pour le suivi, /settle pour vérifier les résultats.")


async def scan_cmd_v44(update, context):
    if update.effective_chat.id == bot.CHAT_ID:
        await run_scan_v44(context, bool(context.args and context.args[0].lower() == "force"))


def main():
    bot.valid_env()
    app = bot.Application.builder().token(bot.TOKEN).build()
    app.add_handler(bot.CommandHandler("start", start_v44))
    app.add_handler(bot.CommandHandler("scan", scan_cmd_v44))
    app.add_handler(bot.CommandHandler("settle", bot.settle_cmd))
    app.add_handler(bot.CommandHandler("stats", bot.stats_cmd))
    app.add_handler(bot.CommandHandler("learn", bot.learn_cmd))
    app.add_handler(bot.CommandHandler("chart", bot.chart_cmd))
    app.add_handler(bot.CommandHandler("resultats", bot.resultats))
    app.add_handler(bot.CallbackQueryHandler(bot.cb))
    app.job_queue.run_daily(bot.job_settle, time=bot.time(hour=bot.SETTLE_HOUR, minute=0, tzinfo=bot.TZ), days=(0,1,2,3,4,5,6), chat_id=bot.CHAT_ID)
    app.job_queue.run_daily(bot.job_scan, time=bot.time(hour=bot.SCAN_HOUR, minute=0, tzinfo=bot.TZ), days=(0,1,2,3,4,5,6), chat_id=bot.CHAT_ID)
    bot.log.info("Oracle Bot V4.4 started mode=%s", bot.MODE)
    app.run_polling(allowed_updates=bot.Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
