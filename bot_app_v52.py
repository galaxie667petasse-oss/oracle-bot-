import bot_app as base
from config import settings
from store import load_db, save_db
from utils import target_day
from shadow_training import build_shadow_candidates

_last_rows = []
_last_displayed = []
_base_select = base.select_picks


def select_picks_with_shadow(rows, top_limit, watch_limit):
    global _last_rows, _last_displayed
    top, watch, rejected = _base_select(rows, top_limit, watch_limit)
    _last_rows = list(rows)
    _last_displayed = list(top) + list(watch)
    return top, watch, rejected


base.select_picks = select_picks_with_shadow


async def run_scan(ctx, force=False):
    await base.run_scan(ctx, force)
    day = target_day()
    db = load_db()
    scan = db.get("scans", {}).get(day["key"])
    if scan is not None and _last_rows:
        shadow = build_shadow_candidates(_last_rows, _last_displayed)
        scan["candidates"] = shadow
        scan["shadow_count"] = len(shadow)
        scan["version"] = "V5.2-SHADOW"
        save_db(db)
        try:
            await ctx.bot.send_message(
                settings.chat_id,
                f"🧪 Apprentissage fantôme activé : {len(shadow)} marchés non affichés seront aussi suivis pour entraîner les agents."
            )
        except Exception:
            pass


async def start_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    await update.message.reply_text(
        "⚽ <b>ORACLE FOOTBALL V5.2</b>\n"
        "━━━━━━━━━━━━━━\n"
        "🤖 Conseil d'agents adaptatif\n"
        "🧠 Poids des agents après GAGNÉ/PERDU\n"
        "🧪 Apprentissage fantôme sur les marchés non affichés\n"
        "✅ Paris conseillés / Observations / Refus\n"
        "🚫 Pas de pari forcé si la value est faible\n"
        "🇫🇷 Interface en français\n"
        "✅ Start Railway fixe: <code>python main.py</code>\n\n"
        "/scan force\n/settle\n/stats\n/chart\n/resultats",
        parse_mode=base.ParseMode.HTML,
    )


async def scan_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await run_scan(context, bool(context.args and context.args[0].lower() == "force"))


async def job_scan(context):
    await run_scan(context, False)


def create_app():
    app = base.create_app()
    # replace handlers by constructing a fresh app, avoiding duplicate command ambiguity
    app = base.Application.builder().token(settings.telegram_token).build()
    app.add_handler(base.CommandHandler("start", start_cmd))
    app.add_handler(base.CommandHandler("scan", scan_cmd))
    app.add_handler(base.CommandHandler("settle", base.settle_cmd))
    app.add_handler(base.CommandHandler("stats", base.stats_cmd))
    app.add_handler(base.CommandHandler("learn", base.stats_cmd))
    app.add_handler(base.CommandHandler("chart", base.chart_cmd))
    app.add_handler(base.CommandHandler("resultats", base.resultats_cmd))
    app.add_handler(base.CallbackQueryHandler(base.callback))
    app.job_queue.run_daily(base.job_settle, time=base.time(hour=settings.settle_hour, minute=0, tzinfo=settings.tz), days=(0,1,2,3,4,5,6), chat_id=settings.chat_id)
    app.job_queue.run_daily(job_scan, time=base.time(hour=settings.scan_hour, minute=0, tzinfo=settings.tz), days=(0,1,2,3,4,5,6), chat_id=settings.chat_id)
    return app


def main():
    base.logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=base.logging.INFO)
    settings.validate()
    app = create_app()
    base.log.info("Oracle V5.2 Shadow Learning started")
    app.run_polling(allowed_updates=base.Update.ALL_TYPES, drop_pending_updates=True)
