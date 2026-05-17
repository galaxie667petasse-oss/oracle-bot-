import bot_app as base
from config import settings
from store import load_db, save_db, settled_picks, settled_records
from utils import target_day, esc
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


def latest_scan(db):
    scans = db.get("scans", {})
    if not scans:
        return None, None
    key = sorted(scans.keys())[-1]
    return key, scans[key]


def memory_text(db):
    learning = db.get("learning", {})
    weights = db.get("agent_weights", {})
    visible = len(settled_picks(db))
    total = len(settled_records(db, include_shadow=True))
    shadow = max(0, total - visible)
    lines = [
        "🧠 <b>MÉMOIRE ORACLE V5.2</b>",
        f"Résultats visibles: <b>{visible}</b>",
        f"Résultats fantômes: <b>{shadow}</b>",
        f"Total appris: <b>{learning.get('samples', total)}</b>",
        "",
        "<b>Poids des agents</b>",
    ]
    if not weights:
        lines.append("• poids neutres pour l'instant")
    else:
        for k, v in weights.items():
            lines.append(f"• {esc(k)}: {v}")
    lines.append("")
    lines.append("Mémoire encore jeune : il faut laisser les résultats s'accumuler avant de juger le niveau réel.")
    return "\n".join(lines)


def report_text(db):
    key, scan = latest_scan(db)
    if not scan:
        return "Aucun scan enregistré."
    picks = scan.get("picks", []) or []
    top = [p for p in picks if p.get("decision") == "ACCEPTE"]
    obs = [p for p in picks if p.get("decision") == "SURVEILLANCE"]
    shadow_count = scan.get("shadow_count", len(scan.get("candidates", []) or []))
    rejected = scan.get("rejected_count", 0)
    return (
        "🧾 <b>RAPPORT DU DERNIER SCAN</b>\n"
        f"Date: <b>{esc(key)}</b>\n"
        f"Version: <b>{esc(scan.get('version', 'V5.2'))}</b>\n"
        f"Paris conseillés: <b>{len(top)}</b>\n"
        f"Observations visibles: <b>{len(obs)}</b>\n"
        f"Marchés refusés: <b>{rejected}</b>\n"
        f"Candidats fantômes: <b>{shadow_count}</b>\n\n"
        "Conclusion: le système entraîne aussi les marchés non affichés pour améliorer les agents sans spam Telegram."
    )


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
                f"🧬 <b>Version active : Oracle V5.2</b>\n🧪 Apprentissage fantôme activé : <b>{len(shadow)}</b> marchés non affichés seront aussi suivis pour entraîner les agents.",
                parse_mode=base.ParseMode.HTML,
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
        "/scan force\n/settle\n/stats\n/memoire\n/rapport\n/chart\n/resultats",
        parse_mode=base.ParseMode.HTML,
    )


async def scan_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await run_scan(context, bool(context.args and context.args[0].lower() == "force"))


async def memoire_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(memory_text(load_db()), parse_mode=base.ParseMode.HTML)


async def rapport_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(report_text(load_db()), parse_mode=base.ParseMode.HTML)


async def job_scan(context):
    await run_scan(context, False)


def create_app():
    app = base.Application.builder().token(settings.telegram_token).build()
    app.add_handler(base.CommandHandler("start", start_cmd))
    app.add_handler(base.CommandHandler("scan", scan_cmd))
    app.add_handler(base.CommandHandler("settle", base.settle_cmd))
    app.add_handler(base.CommandHandler("stats", base.stats_cmd))
    app.add_handler(base.CommandHandler("learn", base.stats_cmd))
    app.add_handler(base.CommandHandler("memoire", memoire_cmd))
    app.add_handler(base.CommandHandler("rapport", rapport_cmd))
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
