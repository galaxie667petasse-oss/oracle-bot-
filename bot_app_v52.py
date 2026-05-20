import io
import json

import bot_app as base
from agents import AGENT_LABELS, agent_weights
from config import settings
from store import build_learning, load_db, save_db, settled_picks, settled_records
from telegram_ui import segments_text
from utils import target_day, esc
from shadow_training import build_shadow_candidates
from persistent_memory import status as persistent_status

_last_rows = []
_last_displayed = []
_last_scan_key = None
_base_select = base.select_picks
_SENSITIVE_EXPORT_KEYS = ("token", "secret", "password", "database_url", "api_key", "apikey")


def select_picks_with_shadow(rows, top_limit, watch_limit):
    global _last_rows, _last_displayed, _last_scan_key
    top, watch, rejected = _base_select(rows, top_limit, watch_limit)
    _last_rows = list(rows)
    _last_displayed = list(top) + list(watch)
    _last_scan_key = _last_rows[0].get("date_key") if _last_rows else None
    return top, watch, rejected


base.select_picks = select_picks_with_shadow


def load_refreshed_db():
    db = load_db()
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    return db


def latest_scan(db):
    scans = db.get("scans", {})
    if not scans:
        return None, None
    key = sorted(scans.keys())[-1]
    return key, scans[key]


def _pending_shadow_count(db):
    n = 0
    for scan in db.get("scans", {}).values():
        for p in scan.get("candidates", []) or []:
            if p.get("result") is None:
                n += 1
    return n


def _pending_visible_count(db):
    n = 0
    for scan in db.get("scans", {}).values():
        for p in scan.get("picks", []) or []:
            if p.get("result") is None:
                n += 1
    return n


def _candidate_count(db):
    return sum(len(scan.get("candidates", []) or []) for scan in db.get("scans", {}).values())


def _risk_warnings(db, mem_status=None):
    warnings = []
    learning = db.get("learning", {}) or {}
    calibration = db.get("calibration", {}) or {}
    agent_samples = int(db.get("agent_weight_samples", 0) or 0)
    if learning.get("samples", 0) > 0 and agent_samples == 0:
        warnings.append("learning > 0 mais agent_weight_samples = 0")
    if mem_status and not mem_status.get("enabled"):
        warnings.append("PostgreSQL absent")
    if not calibration:
        warnings.append("calibration absente")
    risky = []
    for key in ("h2h", "draw"):
        stat = (calibration.get("by_market", {}) or {}).get(key, {})
        if stat and float(stat.get("roi", 0) or 0) < -8:
            risky.append(key)
    for key in ("high", "very_high"):
        stat = (calibration.get("by_odds", {}) or {}).get(key, {})
        if stat and float(stat.get("roi", 0) or 0) < -8:
            risky.append(key)
    if risky:
        warnings.append("beaucoup de ROI négatif sur " + ", ".join(risky))
    return warnings


def memory_text(db):
    learning = db.get("learning", {})
    calibration = db.get("calibration", {}) or {}
    weights = db.get("agent_weights", {})
    visible = len(settled_picks(db))
    total = len(settled_records(db, include_shadow=True))
    shadow_done = max(0, total - visible)
    pending_visible = _pending_visible_count(db)
    pending_shadow = _pending_shadow_count(db)
    mem_status = persistent_status().get("message", "mémoire non vérifiée")
    agent_samples = int(db.get("agent_weight_samples", 0) or 0)
    lines = [
        "🧠 <b>MÉMOIRE ORACLE V5.2</b>",
        f"💾 Stockage: {esc(mem_status)}",
        "",
        "<b>Déjà appris</b>",
        f"• Résultats visibles: <b>{visible}</b>",
        f"• Résultats fantômes: <b>{shadow_done}</b>",
        f"• Total appris: <b>{learning.get('samples', total)}</b>",
        "",
        "<b>En attente de résultats</b>",
        f"• Éléments visibles: <b>{pending_visible}</b>",
        f"• Candidats fantômes: <b>{pending_shadow}</b>",
        "",
        "<b>Calibration</b>",
        f"• Échantillons agents: <b>{agent_samples}</b>",
        f"• Maturité: <b>{esc(calibration.get('maturity_level', 'non calculée'))}</b>",
        f"• Dernière mise à jour: <b>{esc(learning.get('updated_at', 'inconnue'))}</b>",
        "",
        "<b>Poids des agents</b>",
    ]
    if not weights:
        lines.append("• poids neutres pour l'instant")
    else:
        for k, v in weights.items():
            lines.append(f"• {esc(AGENT_LABELS.get(k, k))}: {v}")
    lines.append("")
    if total > 0 and agent_samples == 0:
        lines.append("⚠️ Les résultats sont appris, mais les agents n'ont pas encore de votes exploitables.")
    elif 0 < agent_samples < 30:
        lines.append("Les agents commencent à apprendre, mais l'échantillon reste jeune.")
    if total == 0 and (pending_visible or pending_shadow):
        lines.append("Les marchés sont bien enregistrés, mais ils ne deviennent de l'apprentissage qu'après les scores finaux.")
    else:
        lines.append("Mémoire active : les agents se recalibrent après les résultats réglés.")
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


def diagnostic_text(db):
    mem = persistent_status()
    learning = db.get("learning", {}) or {}
    calibration = db.get("calibration", {}) or {}
    warnings = _risk_warnings(db, mem)
    lines = [
        "🩺 <b>DIAGNOSTIC ORACLE V5.2</b>",
        "• Version active: <b>V5.2 Shadow Learning</b>",
        f"• Stockage: {esc(mem.get('message', 'mémoire non vérifiée'))}",
        f"• Résultats appris: <b>{learning.get('samples', 0)}</b>",
        f"• Échantillons agents: <b>{db.get('agent_weight_samples', 0)}</b>",
        f"• Maturité calibration: <b>{esc(calibration.get('maturity_level', 'absente'))}</b>",
        f"• Scans en DB: <b>{len(db.get('scans', {}))}</b>",
        f"• Candidats fantômes en DB: <b>{_candidate_count(db)}</b>",
        f"• Pending visibles/fantômes: <b>{_pending_visible_count(db)}</b> / <b>{_pending_shadow_count(db)}</b>",
        "",
        "<b>Avertissements</b>",
    ]
    if warnings:
        lines.extend(f"• {esc(w)}" for w in warnings)
    else:
        lines.append("• aucun avertissement critique")
    return "\n".join(lines)


def _safe_export(value):
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _SENSITIVE_EXPORT_KEYS):
                continue
            clean[key] = _safe_export(item)
        return clean
    if isinstance(value, list):
        return [_safe_export(item) for item in value]
    return value


async def run_scan(ctx, force=False):
    global _last_rows, _last_displayed, _last_scan_key
    await base.run_scan(ctx, force)
    day = target_day()
    db = load_db()
    scan = db.get("scans", {}).get(day["key"])
    if scan is not None and _last_rows and _last_scan_key == day["key"]:
        shadow = build_shadow_candidates(_last_rows, _last_displayed)
        scan["candidates"] = shadow
        scan["shadow_count"] = len(shadow)
        scan["version"] = "V5.2-SHADOW"
        save_db(db)
        _last_rows = []
        _last_displayed = []
        _last_scan_key = None
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
        "/scan force\n/settle\n/stats\n/segments\n/memoire\n/rapport\n/diagnostic\n/export\n/chart\n/resultats",
        parse_mode=base.ParseMode.HTML,
    )


async def scan_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await run_scan(context, bool(context.args and context.args[0].lower() == "force"))


async def memoire_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(memory_text(load_refreshed_db()), parse_mode=base.ParseMode.HTML)


async def rapport_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(report_text(load_db()), parse_mode=base.ParseMode.HTML)


async def diagnostic_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(diagnostic_text(load_refreshed_db()), parse_mode=base.ParseMode.HTML)


async def segments_cmd(update, context):
    if update.effective_chat.id == settings.chat_id:
        await update.message.reply_text(segments_text(load_refreshed_db()), parse_mode=base.ParseMode.HTML)


async def export_cmd(update, context):
    if update.effective_chat.id != settings.chat_id:
        return
    payload = json.dumps(_safe_export(load_db()), ensure_ascii=False, indent=2).encode("utf-8")
    if len(payload) > 45 * 1024 * 1024:
        await update.message.reply_text("Export trop volumineux pour Telegram. Utilise un export direct depuis le stockage Railway.")
        return
    bio = io.BytesIO(payload)
    bio.name = "oracle_db_export.json"
    await context.bot.send_document(
        chat_id=settings.chat_id,
        document=bio,
        filename="oracle_db_export.json",
        caption="Export mémoire Oracle Bot, sans variables secrètes.",
    )


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
    app.add_handler(base.CommandHandler("segments", segments_cmd))
    app.add_handler(base.CommandHandler("diagnostic", diagnostic_cmd))
    app.add_handler(base.CommandHandler("export", export_cmd))
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
