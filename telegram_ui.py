from config import settings
from utils import esc
from store import settled_picks, unit_profit, settled_records


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


def pick_card(rank, p, section):
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"][rank - 1] if rank <= 6 else str(rank)
    stake = round(settings.bankroll * (p.get("stake_pct", 0) or 0) / 100, 2)
    ret = round(stake * float(p.get("odds", 1)), 2)
    stake_line = "0 EUR — observation seulement" if stake <= 0 else f"{stake} EUR · retour {ret} EUR · profit +{round(ret - stake, 2)} EUR"
    flags = p.get("outlier_flags") or []
    alert = "\n🚨 <b>Alerte</b> : " + esc(", ".join(flags)) if flags else ""
    resume = p.get("resume") or "Signal analysé par le conseil."
    version = p.get("version") or "V5.2"
    return f"""{medal} <b>{esc(p['home'])} vs {esc(p['away'])}</b>
🏆 {esc(p['competition'])} · ⏰ {esc(p['heure'])} · Qualité {esc(p.get('quality','B-'))}
🧬 Oracle {esc(version)} · <b>{section}</b> · Décision <b>{esc(p.get('decision','SURVEILLANCE'))}</b>

🎯 <b>{esc(p['pari'])}</b>
🧩 Marché : {esc(market_fr(p['market_type']))} · ⚡ cote {p['odds']}
📊 Confiance <b>{p['confidence']}%</b> · ⚠️ Danger <b>{p['danger']}%</b>
💎 Valeur {p['value_score']} · EV <b>{p['ev_pct']}%</b> · cote juste estimée {p.get('fair_odds','?')}
🗳 Score conseil {p.get('council_score', 0)} · ✅ {p.get('agent_accepts', 0)} / ❌ {p.get('agent_rejects', 0)}
💰 Mise : {stake_line}{alert}

🧾 <b>Résumé</b>
{esc(resume)}

🤖 <b>Conseil des agents</b>
{agent_lines(p)}

📝 Enregistré pour suivi automatique demain."""


def stats_text(db):
    visible_rows = settled_picks(db)
    all_rows = settled_records(db, include_shadow=True)
    visible_wins = sum(p["result"] == "win" for p in visible_rows)
    visible_profit = sum(unit_profit(p) for p in visible_rows)
    wr = round(visible_wins / len(visible_rows) * 100, 1) if visible_rows else 0
    roi = round(visible_profit / len(visible_rows) * 100, 1) if visible_rows else 0
    shadow_rows = max(0, len(all_rows) - len(visible_rows))
    backend = db.get("learning", {}).get("memory_backend", "mémoire locale ou non vérifiée")
    lines = [
        "📊 <b>STATS ORACLE V5.2</b>",
        f"🧠 Résultats visibles appris: <b>{len(visible_rows)}</b>",
        f"🧪 Résultats fantômes appris: <b>{shadow_rows}</b>",
        f"📚 Total appris: <b>{len(all_rows)}</b>",
        f"✅ Taux de réussite visible: <b>{wr}%</b> ({visible_wins}/{len(visible_rows)})",
        f"💰 ROI visible: <b>{roi}%</b> · profit {round(visible_profit,2)}u",
        f"💾 Mémoire: {esc(backend)}",
        "",
    ]
    for title, key in [("Marchés", "by_market"), ("Tranches de cotes", "by_odds"), ("Familles de ligues", "by_league")]:
        lines.append(f"<b>{title}</b>")
        data = db.get("learning", {}).get(key, {})
        if not data:
            lines.append("• pas encore assez de données")
        for k, v in data.items():
            lines.append(f"• {esc(k)}: {int(v['w'])}/{int(v['n'])} · réussite {v['wr']}% · ROI {v['roi']}%")
        lines.append("")
    lines.append("<b>Poids des agents</b>")
    lines.append(f"Échantillons agents: <b>{db.get('agent_weight_samples',0)}</b>")
    names = {"marche": "Marché", "valeur": "Valeur", "risque": "Risque", "rythme": "Rythme", "memoire": "Mémoire", "contradiction": "Contradiction"}
    for k, v in db.get("agent_weights", {}).items():
        lines.append(f"• {esc(names.get(k,k))}: {v}")
    return "\n".join(lines)
