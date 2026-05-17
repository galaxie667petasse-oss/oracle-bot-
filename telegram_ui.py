from config import settings
from utils import esc
from store import settled_picks, unit_profit


def agent_lines(p):
    votes = p.get("agent_votes", {})
    labels = [("📈", "Market", "market"), ("💎", "Value", "value"), ("🛡", "Risk", "risk"), ("⚽", "Tempo", "tempo"), ("🧠", "Memory", "memory"), ("⚔️", "Contra", "contradiction")]
    out = []
    for icon, name, key in labels:
        v = votes.get(key, {})
        out.append(f"{icon} <b>{name}</b> : {v.get('vote','?')} - {esc(v.get('note',''))}")
    return "\n".join(out)


def pick_card(rank, p, section):
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"][rank - 1] if rank <= 6 else str(rank)
    stake = round(settings.bankroll * (p.get("stake_pct", 0) or 0) / 100, 2)
    ret = round(stake * float(p.get("odds", 1)), 2)
    stake_line = "0 EUR (observation)" if stake <= 0 else f"{stake} EUR · retour {ret} EUR · profit +{round(ret - stake, 2)} EUR"
    return f"""{medal} <b>{esc(p['home'])} vs {esc(p['away'])}</b>
🏆 {esc(p['competition'])} · ⏰ {esc(p['heure'])} · Qualité {esc(p.get('quality','B-'))}
🧬 Oracle V5 Modular · <b>{section}</b> · Décision <b>{esc(p.get('decision','WATCHLIST'))}</b>

🎯 <b>{esc(p['pari'])}</b>
🧩 {esc(p['market_type'])} · ⚡ cote {p['odds']}
📊 Conf <b>{p['confidence']}%</b> · ⚠️ Danger <b>{p['danger']}%</b>
💎 Value {p['value_score']} · EV <b>{p['ev_pct']}%</b> · ML {p.get('learning_adj', 0)}
🗳 Council {p.get('council_score', 0)} · ✅ {p.get('agent_accepts', 0)} / ❌ {p.get('agent_rejects', 0)}
💰 Mise : {stake_line}

🤖 <b>Conseil des agents</b>
{agent_lines(p)}

📝 Enregistré. Résultat auto demain."""


def stats_text(db):
    rows = settled_picks(db)
    wins = sum(p["result"] == "win" for p in rows)
    profit = sum(unit_profit(p) for p in rows)
    wr = round(wins / len(rows) * 100, 1) if rows else 0
    roi = round(profit / len(rows) * 100, 1) if rows else 0
    lines = ["📊 <b>STATS ORACLE V5 MODULAR</b>", f"🧠 Résultats appris: <b>{len(rows)}</b>", f"✅ Winrate: <b>{wr}%</b> ({wins}/{len(rows)})", f"💰 ROI: <b>{roi}%</b> · profit {round(profit,2)}u", ""]
    for title, key in [("Marchés", "by_market"), ("Cotes", "by_odds"), ("Ligues", "by_league")]:
        lines.append(f"<b>{title}</b>")
        for k, v in db.get("learning", {}).get(key, {}).items():
            lines.append(f"• {esc(k)}: {int(v['w'])}/{int(v['n'])} · WR {v['wr']}% · ROI {v['roi']}%")
        lines.append("")
    lines.append("<b>Poids agents</b>")
    lines.append(f"Samples agents: <b>{db.get('agent_weight_samples',0)}</b>")
    for k, v in db.get("agent_weights", {}).items():
        lines.append(f"• {esc(k)}: {v}")
    return "\n".join(lines)
