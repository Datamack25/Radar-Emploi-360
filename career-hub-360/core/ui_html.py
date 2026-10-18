"""Morceaux HTML/CSS de l'interface (toutes les valeurs venant des offres sont échappées)."""
from __future__ import annotations

import html
from urllib.parse import urlparse

from .filters import FAMILIES

CAT_COLORS = {"Banque": "#1D4ED8", "Fintech / PSP": "#7C3AED", "Crypto": "#B45309", "Transfert d'argent": "#0E7490",
              "RegTech": "#9333EA", "Cabinet": "#0F766E", "Assurance": "#BE185D", "Gestion d'actifs": "#4338CA",
              "Régulateur / public": "#374151", "Recrutement / intérim": "#64748B", "Autre": "#6B7280"}
FAM_COLORS = {"conformite": "#2A9D8F", "ba": "#E76F51", "credit": "#264653", "profil": "#7C3AED"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def safe_url(u) -> str:
    u = str(u or "").strip()
    return u if urlparse(u).scheme in ("http", "https") else "https://candidat.francetravail.fr"


CSS = """<style>
:root{--rc-ink:#0f172a;--rc-muted:#64748b;--rc-line:#e2e8f0;--rc-card:#ffffff;--rc-soft:#f8fafc;--rc-accent:#ff7a45}
@media (prefers-color-scheme: dark){:root{--rc-ink:#e2e8f0;--rc-muted:#94a3b8;--rc-line:#334155;--rc-card:#111827;--rc-soft:#1e293b}}
.rc-hero{background:linear-gradient(120deg,#0f172a 0%,#1e3a5f 60%,#2A9D8F 130%);color:#fff;border-radius:18px;padding:22px 26px;margin-bottom:10px}
.rc-hero h1{font-size:1.65rem;margin:0 0 4px 0;color:#fff}
.rc-hero p{margin:0;opacity:.85;font-size:.92rem}
.rc-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.rc-pill{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:3px 11px;font-size:.8rem}
.rc-notice{border-radius:12px;padding:10px 14px;font-size:.88rem;border:1px solid}
.rc-notice.warn{background:#fff7ed;border-color:#fdba74;color:#7c2d12}
.rc-notice.info{background:#eff6ff;border-color:#93c5fd;color:#1e3a8a}
.rc-notice.ok{background:#f0fdf4;border-color:#86efac;color:#14532d}
.rc-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:6px 0 14px}
.rc-kpi{background:var(--rc-card);border:1px solid var(--rc-line);border-radius:14px;padding:10px 12px}
.rc-kpi b{display:block;font-size:1.45rem;line-height:1.2}
.rc-kpi span{font-size:.75rem;color:var(--rc-muted)}
.rc-card{background:var(--rc-card);border:1px solid var(--rc-line);border-radius:16px;padding:14px 16px 10px;position:relative}
.rc-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.rc-title{font-weight:700;font-size:1.02rem;color:var(--rc-ink);line-height:1.3}
.rc-comp{color:var(--rc-muted);font-size:.86rem;margin-top:2px}
.rc-score{min-width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;font-size:.95rem}
.rc-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.rc-chip{font-size:.74rem;border-radius:999px;padding:2px 9px;background:var(--rc-soft);border:1px solid var(--rc-line);color:var(--rc-ink)}
.rc-chip.c{color:#fff;border:none}
.rc-chip.good{background:#dcfce7;border-color:#86efac;color:#14532d}
.rc-chip.warn{background:#fef3c7;border-color:#fcd34d;color:#78350f}
.rc-new{position:absolute;top:-9px;left:14px;background:var(--rc-accent);color:#fff;font-size:.68rem;font-weight:700;border-radius:999px;padding:1px 8px}
.rc-meta{font-size:.75rem;color:var(--rc-muted);margin-top:8px}
.rc-empty{text-align:center;padding:40px 10px;border:1px dashed var(--rc-line);border-radius:16px;color:var(--rc-muted)}
.rc-empty b{display:block;color:var(--rc-ink);font-size:1.05rem;margin-bottom:4px}
.rc-desc{font-size:.88rem;line-height:1.55;max-height:420px;overflow:auto;border:1px solid var(--rc-line);border-radius:12px;padding:12px;background:var(--rc-soft)}
.rc-bd{width:100%;border-collapse:collapse;font-size:.85rem}
.rc-bd td{padding:4px 6px;border-bottom:1px solid var(--rc-line)}
.rc-bd td:last-child{text-align:right;font-weight:700;white-space:nowrap}
.rc-source{font-size:.78rem;color:var(--rc-muted);margin:6px 0}
.rc-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.rc-tile{border:1px solid var(--rc-line);border-radius:14px;padding:10px 12px;background:var(--rc-card)}
.rc-tile b{display:block}
.rc-tile small{color:var(--rc-muted)}
div[class*="st-key-maj"] button{background:var(--rc-accent)!important;color:#fff!important;border:none!important;font-weight:700;min-height:48px}
</style>"""


def hero(nom, subtitle, last, pills) -> str:
    p = "".join(f'<span class="rc-pill">{esc(x)}</span>' for x in pills)
    who = f" — {esc(nom)}" if nom else ""
    return (f'<div class="rc-hero"><h1>🎯 Radar Emploi{who}</h1><p>{esc(subtitle)}</p>'
            f'<p style="margin-top:4px">Dernière mise à jour : {esc(last)}</p><div class="rc-pills">{p}</div></div>')


def notice(kind, text) -> str:
    return f'<div class="rc-notice {esc(kind)}">{esc(text)}</div>'


def kpis(items) -> str:
    return '<div class="rc-kpis">' + "".join(
        f'<div class="rc-kpi"><b style="color:{esc(c)}">{esc(v)}</b><span>{esc(l)}</span></div>' for l, v, c in items) + "</div>"


def empty_state(title, text) -> str:
    return f'<div class="rc-empty"><b>{esc(title)}</b>{esc(text)}</div>'


def _score_color(s) -> str:
    return "#16a34a" if s >= 75 else "#2A9D8F" if s >= 60 else "#f59e0b" if s >= 45 else "#94a3b8"


def contract_label(r) -> str:
    k, m = r.get("contract") or "Non précisé", r.get("duration")
    if k in ("CDD", "Intérim"):
        return f"{k} · {int(m)} mois" if m else f"{k} · durée non précisée"
    return "Contrat non précisé" if k == "Non précisé" else k


def salary_label(r) -> str:
    lo, hi = r.get("salary_min"), r.get("salary_max")
    if not (lo or hi):
        return "Salaire non précisé"
    lo, hi = round((lo or hi) / 1000), round((hi or lo) / 1000)
    return f"{lo} k€ / an" if lo == hi else f"{lo}–{hi} k€ / an"


def offer_card(r, is_new, age, source_name) -> str:
    cat = r.get("category") or "Autre"
    fam = r.get("family") or "conformite"
    sal = salary_label(r)
    exp = r.get("experience") or "Expérience non précisée"
    chips = [
        f'<span class="rc-chip c" style="background:{FAM_COLORS.get(fam, "#2A9D8F")}">{esc(FAMILIES.get(fam, fam))}</span>',
        f'<span class="rc-chip c" style="background:{CAT_COLORS.get(cat, "#6B7280")}">{esc(cat)}</span>',
        f'<span class="rc-chip">📍 {esc(r.get("location") or "Lieu non précisé")}</span>',
        f'<span class="rc-chip">📄 {esc(contract_label(r))}</span>',
        f'<span class="rc-chip {"good" if r.get("salary_max") else ""}">💶 {esc(sal)}</span>',
        f'<span class="rc-chip {"good" if (r.get("exp_min") == 0 or "Débutant" in exp or "Junior" in exp) else ""}">🎓 {esc(exp)}</span>',
    ]
    new = '<span class="rc-new">NOUVELLE</span>' if is_new else ""
    v = (r.get("extra") or {}).get("via")
    via = f" ({esc(v)})" if v else ""
    return (f'<div class="rc-card">{new}<div class="rc-top"><div><div class="rc-title">{esc(r.get("title"))}</div>'
            f'<div class="rc-comp">{esc(r.get("company"))}{" · " + esc(r["region"]) if r.get("region") else ""}</div></div>'
            f'<div class="rc-score" style="background:{_score_color(r.get("score", 0))}" title="Score de pertinence">{esc(r.get("score", 0))}</div></div>'
            f'<div class="rc-chips">{"".join(chips)}</div>'
            f'<div class="rc-meta">Publiée {esc(age)} · via {esc(source_name)}{via} · statut : {esc(r.get("status", ""))}</div></div>')


def description_html(text) -> str:
    return f'<div class="rc-desc">{esc(text or "Texte non fourni par la source.").replace(chr(10), "<br>")}</div>'


def breakdown_html(parts) -> str:
    rows = "".join(f"<tr><td>{esc(l)}</td><td>+{esc(p)}</td></tr>" for l, p in (parts or []))
    return f'<table class="rc-bd">{rows}</table>'


def source_tiles(per_source) -> str:
    icon = {"ok": "✅", "erreur": "⚠️", "désactivée": "⚪"}
    out = []
    for s in per_source:
        detail = (f"{s.get('fetched', 0)} lues · {s.get('kept', 0)} retenues" if s["status"] == "ok" else s.get("message", ""))
        out.append(f'<div class="rc-tile"><b>{icon.get(s["status"], "•")} {esc(s["label"])}</b><small>{esc(detail)}</small></div>')
    return '<div class="rc-tiles">' + "".join(out) + "</div>"
