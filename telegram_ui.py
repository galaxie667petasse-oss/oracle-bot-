from config import settings
from utils import esc
from store import league_bucket, odds_bucket, settled_picks, unit_profit, settled_records
from agents import AGENTS, AGENT_LABELS, agent_outcome_counts
from segment_analysis import build_segment_report


def agent_lines(p):
    votes = p.get("agent_votes", {})
    labels = [("📈", "Marché", "marche"), ("💎", "Valeur", "valeur"), ("🛡", "Risque", "risque"), ("⚽", "Rythme", "rythme"), ("🧠", "Mémoire", "memoire"), ("⚔️", "Contradiction", "contradiction")]
    out = []
    for icon, name, key in labels:
        v = votes.get(key, {})
        out.append(f"{icon} <b>{name}</b> : {esc(v.get('vote','?'))} — {esc(v.get('note',''))}")
    return "\n".join(out)


def market_fr(market):
    return {"h2h": "Victoire simple", "draw": "Match nul", "total": "Buts", "btts": "Les deux marquent"}.get(market, market)


def _settled_candidates(db):
    rows = []
    for scan in db.get("scans", {}).values():
        for p in scan.get("candidates", []) or []:
            if p.get("result") in ("win", "loss"):
                rows.append(p)
    return rows


def _summary(rows):
    wins = sum(p.get("result") == "win" for p in rows)
    profit = sum(unit_profit(p) for p in rows)
    n = len(rows)
    wr = round(wins / n * 100, 1) if n else 0
    roi = round(profit / n * 100, 1) if n else 0
    return n, wins, wr, roi, round(profit, 2)


def _summary_line(label, rows):
    n, wins, wr, roi, profit = _summary(rows)
    return f"• {label}: <b>{n}</b> · {wins}/{n} · réussite observée {wr}% · ROI {roi}% · {profit}u"


def _group_rows(rows, key_fn):
    grouped = {}
    for p in rows:
        grouped.setdefault(key_fn(p), []).append(p)
    return grouped


def _group_lines(rows, key_fn, order=None, empty="pas encore assez de données"):
    grouped = _group_rows(rows, key_fn)
    keys = order or sorted(grouped.keys())
    lines = []
    for key in keys:
        group = grouped.get(key, [])
        if group:
            lines.append(_summary_line(str(key), group))
    return lines or [f"• {empty}"]


def _decision_lines(rows):
    key_fn = lambda p: p.get("decision") or ("REFUSE" if p.get("shadow") else "INCONNU")
    grouped = _group_rows(rows, key_fn)
    lines = [_summary_line(decision, grouped.get(decision, [])) for decision in ("ACCEPTE", "SURVEILLANCE", "REFUSE")]
    if grouped.get("INCONNU"):
        lines.append(_summary_line("INCONNU", grouped["INCONNU"]))
    return lines


def _maturity_message(total):
    if total < 30:
        return "Mémoire trop jeune : lecture prudente, les tendances peuvent bouger vite."
    if total < 100:
        return "Calibration en cours : les tendances deviennent utiles mais restent à confirmer."
    return "Statistiques plus exploitables : assez d'historique pour mieux pondérer les signaux."


def _fmt_list(values):
    if not values:
        return "aucun"
    if isinstance(values, dict):
        return ", ".join(str(k) for k in values.keys()) or "aucun"
    return ", ".join(str(v) for v in values) or "aucun"


def _negative_history_alert(db):
    calibration = db.get("calibration", {}) or {}
    by_market = calibration.get("by_market", {}) or db.get("learning", {}).get("by_market", {}) or {}
    by_odds = calibration.get("by_odds", {}) or db.get("learning", {}).get("by_odds", {}) or {}
    risky = []
    for key in ("h2h", "draw"):
        stat = by_market.get(key, {}) or {}
        if stat and float(stat.get("roi", 0) or 0) < 0:
            risky.append(key)
    for key in ("high", "very_high"):
        stat = by_odds.get(key, {}) or {}
        if stat and float(stat.get("roi", 0) or 0) < 0:
            risky.append(key)
    if risky:
        return "⚠️ Historique défavorable : le bot doit rester très strict sur ces catégories."
    return ""


def _top_agents(counts, field, limit=2):
    ranked = sorted(
        ((agent, stat[field]) for agent, stat in counts.items() if stat[field] > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return "pas assez de votes tranchés"
    return ", ".join(f"{AGENT_LABELS.get(agent, agent)} ({value})" for agent, value in ranked[:limit])


def _weight_changes(before, after):
    changes = []
    for agent in AGENTS:
        old = float(before.get(agent, 1.0) or 1.0)
        new = float(after.get(agent, 1.0) or 1.0)
        delta = round(new - old, 2)
        if abs(delta) >= 0.01:
            sign = "+" if delta > 0 else ""
            changes.append(f"{AGENT_LABELS.get(agent, agent)} {sign}{delta}")
    return ", ".join(changes[:4]) if changes else "poids stables"


def settlement_summary(result, before_weights, after_weights):
    rows = result.get("settled_rows", []) or []
    counts = agent_outcome_counts(rows)
    return "\n".join([
        "🧾 <b>Règlement terminé</b>",
        f"• Visibles réglés: <b>{result.get('visible_settled', 0)}</b>",
        f"• Fantômes réglés: <b>{result.get('shadow_settled', 0)}</b>",
        f"• Bilan: ✅ {result.get('wins', 0)} gagnés · ❌ {result.get('losses', 0)} perdus · ⏳ {result.get('pending', 0)} en attente",
        f"• Agents souvent justes: {esc(_top_agents(counts, 'right'))}",
        f"• Agents à surveiller: {esc(_top_agents(counts, 'wrong'))}",
        f"• Poids: {esc(_weight_changes(before_weights, after_weights))}",
        "Lecture prudente : ces réglages servent à calibrer, pas à promettre un résultat.",
    ])


def pick_card(rank, p, section):
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"][rank - 1] if rank <= 6 else str(rank)
    stake = round(settings.bankroll * (p.get("stake_pct", 0) or 0) / 100, 2)
    ret = round(stake * float(p.get("odds", 1)), 2)
    stake_line = "0 EUR — observation seulement" if stake <= 0 else f"{stake} EUR · retour {ret} EUR · profit +{round(ret - stake, 2)} EUR"
    flags = p.get("outlier_flags") or []
    alert = "\n🚨 <b>Alerte</b> : " + esc(", ".join(flags)) if flags else ""
    resume = p.get("resume") or "Signal analysé par le conseil."
    version = p.get("version") or "V5.2"
    segment_line = ""
    if p.get("segment_n"):
        roi = float(p.get("segment_roi", 0) or 0)
        tone = "favorable" if roi > 2 else "défavorable" if roi < -8 else "neutre"
        segment_line = f"\n📚 Segment historique : <b>{tone}</b> · {esc(p.get('segment_label', 'segment'))} · ROI {p.get('segment_roi')}% · n={p.get('segment_n')}"
    return f"""{medal} <b>{esc(p['home'])} vs {esc(p['away'])}</b>
🏆 {esc(p['competition'])} · ⏰ {esc(p['heure'])} · Qualité {esc(p.get('quality','B-'))}
🧬 Oracle {esc(version)} · <b>{section}</b> · Décision <b>{esc(p.get('decision','SURVEILLANCE'))}</b>

🎯 <b>{esc(p['pari'])}</b>
🧩 Marché : {esc(market_fr(p['market_type']))} · ⚡ cote {p['odds']}
📊 Confiance <b>{p['confidence']}%</b> · ⚠️ Danger <b>{p['danger']}%</b>
💎 Valeur {p['value_score']} · EV <b>{p['ev_pct']}%</b> · cote juste estimée {p.get('fair_odds','?')}
🗳 Score conseil {p.get('council_score', 0)} · ✅ {p.get('agent_accepts', 0)} / ❌ {p.get('agent_rejects', 0)}{segment_line}
💰 Mise : {stake_line}{alert}

🧾 <b>Résumé</b>
{esc(resume)}

🤖 <b>Conseil des agents</b>
{agent_lines(p)}

📝 Enregistré pour suivi automatique demain."""


def stats_text(db):
    visible_rows = settled_picks(db)
    shadow_rows = _settled_candidates(db)
    all_rows = settled_records(db, include_shadow=True)
    learning = db.get("learning", {}) or {}
    calibration = db.get("calibration", {}) or {}
    agent_samples = int(db.get("agent_weight_samples", 0) or 0)
    backend = db.get("learning", {}).get("memory_backend", "mémoire locale ou non vérifiée")
    lines = [
        "📊 <b>STATS ORACLE V5.2</b>",
        f"🧠 Résultats visibles appris: <b>{len(visible_rows)}</b>",
        f"🧪 Résultats fantômes appris: <b>{len(shadow_rows)}</b>",
        f"📚 Total appris: <b>{len(all_rows)}</b>",
        f"🧭 Maturité: <b>{esc(calibration.get('maturity_level') or _maturity_message(len(all_rows)))}</b>",
        f"💾 Mémoire: {esc(backend)}",
        "",
        "<b>Calibration active</b>",
        f"• EV minimum top: <b>{calibration.get('min_ev_for_top', '?')}</b>",
        f"• Score conseil minimum top: <b>{calibration.get('min_council_score_for_top', '?')}</b>",
        f"• Danger max top: <b>{calibration.get('max_danger_for_top', '?')}</b>",
        f"• Max cote H2H top: <b>{calibration.get('max_h2h_odds_for_top', '?')}</b>",
        f"• Marchés pénalisés: {esc(_fmt_list(calibration.get('banned_or_penalized_markets', {})))}",
        f"• Tranches pénalisées: {esc(_fmt_list(calibration.get('banned_or_penalized_odds_buckets', {})))}",
        "",
        "<b>Synthèse observée</b>",
        _summary_line("Visibles seulement", visible_rows),
        _summary_line("Fantômes seulement", shadow_rows),
        _summary_line("Global visibles + fantômes", all_rows),
        "",
        "<b>Par décision</b>",
        *_decision_lines(all_rows),
        "",
    ]
    for title, key_fn in [
        ("Marchés", lambda p: market_fr(p.get("market_type", "?"))),
        ("Tranches de cotes", lambda p: odds_bucket(float(p.get("odds", 2.0) or 2.0))),
        ("Familles de ligues", lambda p: league_bucket(p.get("competition", ""))),
    ]:
        lines.append(f"<b>{title}</b>")
        lines.extend(_group_lines(all_rows, key_fn))
        lines.append("")
    lines.append("<b>Poids des agents</b>")
    lines.append(f"Échantillons agents: <b>{agent_samples}</b>")
    for k, v in db.get("agent_weights", {}).items():
        lines.append(f"• {esc(AGENT_LABELS.get(k,k))}: {v}")
    if learning.get("samples", 0) and agent_samples == 0:
        lines.append("")
        lines.append("⚠️ Résultats appris présents, mais aucun vote agent exploitable. Recalcule /stats ou réimporte avec votes historiques.")
    alert = _negative_history_alert(db)
    if alert:
        lines.append("")
        lines.append(alert)
    return "\n".join(lines)


def _segment_line(rank, segment):
    return (
        f"{rank}. {esc(segment.get('label', '?'))} — "
        f"ROI {segment.get('roi', 0)}%, n={segment.get('n', 0)}, "
        f"réussite {segment.get('winrate', 0)}%, cote moy. {segment.get('average_odds', 0)}"
    )


def segments_text(db):
    report = db.get("segment_report") or build_segment_report(db)
    samples = int(report.get("samples", 0) or 0)
    positives = report.get("positive_segments", []) or []
    best = report.get("best_segments", []) or []
    worst = report.get("worst_segments", []) or []
    lines = [
        "📊 <b>SEGMENTS HISTORIQUES</b>",
        f"Échantillons: <b>{samples}</b>",
    ]
    if positives:
        lines.append(f"Segments positifs fiables: <b>{len(positives)}</b>")
    else:
        lines.append("Aucun segment positif fiable détecté.")
    lines.extend(["", "<b>Moins mauvais / positifs</b>"])
    if best:
        lines.extend(_segment_line(i, seg) for i, seg in enumerate(best[:5], 1))
    else:
        lines.append("pas encore assez de volume exploitable")
    lines.extend(["", "<b>À éviter</b>"])
    if worst:
        lines.extend(_segment_line(i, seg) for i, seg in enumerate(worst[:5], 1))
    else:
        lines.append("aucun segment négatif fort détecté")
    lines.append("")
    lines.append("Lecture prudente : un segment favorable ne force jamais un pari, il limite seulement la pénalité si le reste du signal est solide.")
    return "\n".join(lines)
