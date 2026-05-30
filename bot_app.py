import io
import logging
from datetime import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import settings
from store import load_db, save_db, build_learning, pending_picks, settled_picks, unit_profit
from providers import odds_matches
from scoring import market_pool, score_pick
from agents import council, select_picks, agent_weights
from settlement import auto_settle
from telegram_ui import pick_card, settlement_summary, stats_text
from utils import target_day, esc

log = logging.getLogger("oracle_v51")


def build_rows(matches, db):
    rows = []
    for item in market_pool(matches, db)[: settings.max_analyzed]:
        m, c = item["match"], item["candidate"]
        sc = score_pick(m, c, item["prefilter_score"], db)
        p = {
            "match_id": m["id"], "date_key": m["date_key"], "home": m["home"], "away": m["away"],
            "competition": m["competition"], "heure": m["heure"], "source": m["source"], "bookmaker": m["bookmaker"],
            "pari": c["pari"], "market_type": c["type"], "odds": round(c["odds"], 2), "result": None, **sc
        }
        p.update(council(p, db))
        rows.append(p)
    return rows


async def run_scan(ctx, force=False):
    await auto_settle(ctx, False)
    db = load_db()
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    day = target_day()

    if not force and db["scans"].get(day["key"], {}).get("picks"):
        await ctx.bot.send_message(settings.chat_id, "Scan déjà fait. Utilise /scan force pour refaire l'analyse.")
        return

    msg = await ctx.bot.send_message(
        settings.chat_id,
        f"🔎 <b>Oracle V5.1 — Calibration</b>\n📅 {day['label']} · Mode {settings.mode}\n🧠 Résultats appris: {db['learning'].get('samples',0)}\n🤖 Conseil d'agents adaptatif actif\nRecherche des marchés...",
        parse_mode=ParseMode.HTML,
    )
    matches = await odds_matches(day["key"])
    if not matches:
        await msg.edit_text("Aucun match avec cotes trouvé aujourd'hui.")
        return

    rows = build_rows(matches, db)
    top, watch, rejected = select_picks(rows, settings.top_picks, settings.watchlist_limit)
    displayed = top + watch
    db["scans"][day["key"]] = {
        "date_key": day["key"], "date_label": day["label"], "scanned_at": day["at"],
        "mode": settings.mode, "version": settings.version, "picks": displayed, "rejected_count": len(rejected),
    }
    save_db(db)

    if top:
        verdict = "Des opportunités passent les filtres du conseil."
    elif watch:
        verdict = "Aucun pari fort conseillé : uniquement des signaux en observation."
    else:
        verdict = "Journee sans selection activee : le conseil refuse de forcer un ticket."

    await msg.edit_text(
        f"🧬 <b>Oracle V5.1 — Calibration</b>\n📅 {esc(day['label'])}\n🏆 Paris conseillés: <b>{len(top)}</b>\n👀 Observations: <b>{len(watch)}</b>\n🚫 Marchés refusés: <b>{len(rejected)}</b>\n\n🧾 <b>Résumé</b>\n{esc(verdict)}\n\n✅ Les éléments affichés sont enregistrés pour vérification automatique à {settings.settle_hour}h.",
        parse_mode=ParseMode.HTML,
    )

    if top:
        await ctx.bot.send_message(settings.chat_id, "🏆 <b>PARIS CONSEILLÉS — validés par le conseil</b>", parse_mode=ParseMode.HTML)
        for i, p in enumerate(top, 1):
            idx = displayed.index(p)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ GAGNÉ", callback_data=f"res:{day['key']}:{idx}:win"), InlineKeyboardButton("❌ PERDU", callback_data=f"res:{day['key']}:{idx}:loss"), InlineKeyboardButton("🚫 Annuler", callback_data=f"res:{day['key']}:{idx}:cancel")]])
            await ctx.bot.send_message(settings.chat_id, pick_card(i, p, "OBSERVATION"), parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await ctx.bot.send_message(settings.chat_id, "🏆 <b>OBSERVATIONS ORACLE</b>\nAucune selection activee aujourd'hui. Le systeme prefere ne rien jouer plutot que forcer une selection faible.", parse_mode=ParseMode.HTML)

    if watch:
        await ctx.bot.send_message(settings.chat_id, "👀 <b>OBSERVATIONS — suivi statistique, pas de mise conseillée</b>", parse_mode=ParseMode.HTML)
        for i, p in enumerate(watch, 1):
            idx = displayed.index(p)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ GAGNÉ", callback_data=f"res:{day['key']}:{idx}:win"), InlineKeyboardButton("❌ PERDU", callback_data=f"res:{day['key']}:{idx}:loss"), InlineKeyboardButton("🚫 Annuler", callback_data=f"res:{day['key']}:{idx}:cancel")]])
            await ctx.bot.send_message(settings.chat_id, pick_card(i, p, "OBSERVATION"), parse_mode=ParseMode.HTML, reply_markup=kb)

    await ctx.bot.send_message(settings.chat_id, "✅ Analyse terminée. Les résultats futurs recalibreront les agents.")


async def start_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    await update.message.reply_text(
        "⚽ <b>ORACLE FOOTBALL V5.1</b>\n━━━━━━━━━━━━━━\n🤖 Conseil d'agents adaptatif\n🧠 Poids des agents après GAGNÉ/PERDU\n✅ Paris conseillés / Observations / Refus\n🚫 Pas de pari forcé si la value est faible\n🇫🇷 Interface en français\n✅ Start Railway fixe: <code>python main.py</code>\n\n/scan force\n/settle\n/stats\n/chart\n/resultats",
        parse_mode=ParseMode.HTML,
    )


async def scan_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await run_scan(context, bool(context.args and context.args[0].lower() == "force"))


async def settle_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    before_db = load_db()
    before_weights = dict(before_db.get("agent_weights", {}))
    r = await auto_settle(context, True)
    db = load_db()
    db["learning"] = build_learning(db)
    agent_weights(db)
    after_weights = dict(db.get("agent_weights", {}))
    save_db(db)
    await update.message.reply_text(settlement_summary(r, before_weights, after_weights), parse_mode=ParseMode.HTML)


async def stats_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    db = load_db()
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    await update.message.reply_text(stats_text(db), parse_mode=ParseMode.HTML)


async def resultats_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    pending = list(pending_picks(load_db()))
    if not pending:
        await update.message.reply_text("✅ Aucun élément en attente.")
        return
    await update.message.reply_text(f"⏳ {len(pending)} éléments en attente. /settle pour vérifier automatiquement.")
    for date_key, _, p in pending[:10]:
        await update.message.reply_text(f"{date_key}\n{p['home']} vs {p['away']}\n{p['pari']} · {p.get('decision','?')} · confiance {p['confidence']}%")


async def chart_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    rows = settled_picks(load_db())
    if not rows:
        await update.message.reply_text("Pas encore assez de résultats pour générer le graphique.")
        return
    try:
        import matplotlib.pyplot as plt
        x, y, c = [], [], 0
        for i, p in enumerate(rows, 1):
            c += unit_profit(p)
            x.append(i); y.append(c)
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(x, y, marker="o")
        ax.axhline(0, linewidth=1)
        ax.grid(True, alpha=.3)
        ax.set_title("Oracle V5.1 - Profit cumulé")
        bio = io.BytesIO()
        fig.tight_layout()
        fig.savefig(bio, format="png", dpi=150)
        plt.close(fig)
        bio.seek(0)
        await context.bot.send_photo(settings.chat_id, bio, caption="📈 Performance cumulée")
    except Exception as exc:
        await update.message.reply_text(f"Graphique indisponible: {esc(exc)}")


async def callback(update, context):
    q = update.callback_query
    await q.answer()
    if q.message.chat_id != settings.chat_id or not q.data.startswith("res:"):
        return
    _, date_key, idx_s, result = q.data.split(":")
    db = load_db()
    scan = db["scans"].get(date_key)
    idx = int(idx_s)
    if not scan or idx >= len(scan.get("picks", [])):
        await q.edit_message_text("Élément introuvable.")
        return
    scan["picks"][idx]["result"] = "cancelled" if result == "cancel" else result
    scan["picks"][idx]["manual_result"] = True
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    await q.edit_message_text((q.message.text_html or q.message.text) + f"\n\n{'✅ GAGNÉ' if result=='win' else '❌ PERDU' if result=='loss' else '🚫 Annulé'} enregistré.", parse_mode=ParseMode.HTML)


async def job_settle(context):
    await auto_settle(context, False)
    db = load_db()
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)


async def job_scan(context):
    await run_scan(context, False)


def create_app():
    settings.validate()
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("settle", settle_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("learn", stats_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(CommandHandler("resultats", resultats_cmd))
    app.add_handler(CallbackQueryHandler(callback))
    app.job_queue.run_daily(job_settle, time=time(hour=settings.settle_hour, minute=0, tzinfo=settings.tz), days=(0,1,2,3,4,5,6), chat_id=settings.chat_id)
    app.job_queue.run_daily(job_scan, time=time(hour=settings.scan_hour, minute=0, tzinfo=settings.tz), days=(0,1,2,3,4,5,6), chat_id=settings.chat_id)
    return app


def main():
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
    app = create_app()
    log.info("Oracle V5.1 Calibration started")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
