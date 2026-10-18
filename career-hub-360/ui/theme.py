"""Thème et morceaux HTML communs (les valeurs venant des offres ou de l'IA sont toujours échappées)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from core.ui_html import CSS as RADAR_CSS
from core.ui_html import esc, safe_url

PARIS = ZoneInfo("Europe/Paris")

CSS = RADAR_CSS + """<style>
.ch-hero{background:linear-gradient(120deg,#0b1324 0%,#1e3a5f 55%,#2A9D8F 120%);color:#fff;border-radius:18px;padding:22px 26px;margin-bottom:12px}
.ch-hero h1{font-size:1.7rem;margin:0 0 4px 0;color:#fff;letter-spacing:-.01em}
.ch-hero p{margin:0;opacity:.88;font-size:.93rem}
.ch-agents{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:8px 0 14px}
@media (min-width:1200px){.ch-agents{grid-template-columns:repeat(5,1fr)}}
.ch-agent{background:var(--rc-card);border:1px solid var(--rc-line);border-radius:16px;padding:14px 14px 12px;position:relative}
.ch-agent .ic{font-size:1.5rem}
.ch-agent b{display:block;color:var(--rc-ink);margin:4px 0 2px;font-size:.98rem}
.ch-agent p{font-size:.8rem;color:var(--rc-muted);margin:0 0 8px;line-height:1.4}
.ch-state{font-size:.74rem;border-radius:999px;padding:2px 9px;display:inline-block}
.ch-state.ok{background:#dcfce7;color:#14532d}.ch-state.partiel{background:#fef3c7;color:#78350f}.ch-state.manque{background:#fee2e2;color:#7f1d1d}
.ch-last{font-size:.72rem;color:var(--rc-muted);margin-top:6px}
.ch-page{display:flex;gap:12px;align-items:center;margin:2px 0 10px}
.ch-page .ic{font-size:2rem}
.ch-page h2{margin:0;font-size:1.45rem}
.ch-page p{margin:2px 0 0;color:var(--rc-muted);font-size:.9rem}
.ch-io{font-size:.78rem;color:var(--rc-muted);margin-bottom:10px}
.ch-src{font-size:.86rem;line-height:1.7}
.ch-src a{color:#1d4ed8}
.ch-diff{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}
.ch-diff div{border:1px solid var(--rc-line);border-radius:10px;padding:8px 10px;font-size:.84rem}
.ch-diff .old{background:#fef2f2;color:#7f1d1d}.ch-diff .new{background:#f0fdf4;color:#14532d}
.ch-why{font-size:.76rem;color:var(--rc-muted);margin:-4px 0 10px}
.ch-score{display:flex;gap:14px;align-items:center;margin:8px 0}
.ch-score b{font-size:1.6rem}
@media (prefers-color-scheme: dark){.ch-diff .old{background:#3b1212;color:#fecaca}.ch-diff .new{background:#0f2e1b;color:#bbf7d0}}
div[class*="st-key-maj"] button,div[class*="st-key-go_"] button{background:var(--rc-accent)!important;color:#fff!important;border:none!important;font-weight:700;min-height:46px}
</style>"""


def inject():
    st.html(CSS)


def page_header(info, extra: str = ""):
    st.html(f'<div class="ch-page"><span class="ic">{esc(info.icone)}</span><div><h2>{esc(info.nom)}</h2>'
            f'<p>{esc(info.mission)}</p></div></div>'
            f'<div class="ch-io"><b>Entrées</b> : {esc(" · ".join(info.entrees))} &nbsp;|&nbsp; <b>Sorties</b> : '
            f'{esc(" · ".join(info.sorties))}{(" &nbsp;|&nbsp; " + esc(extra)) if extra else ""}</div>')


def agent_card(info, state: str, msg: str, last: dict | None) -> str:
    lab = {"ok": "Prêt", "partiel": "À compléter", "manque": "Action requise"}.get(state, state)
    last_txt = ""
    if last:
        icon = "✅" if last.get("ok") else "⚠️"
        last_txt = f'<div class="ch-last">{icon} Dernière exécution : {esc(fmt_dt(last.get("finished")))} — {esc(last.get("summary", ""))}</div>'
    return (f'<div class="ch-agent"><span class="ic">{esc(info.icone)}</span><b>{esc(info.nom)}</b><p>{esc(info.mission)}</p>'
            f'<span class="ch-state {esc(state)}">{esc(lab)}</span> <span style="font-size:.76rem">{esc(msg)}</span>{last_txt}</div>')


def sources_html(sources: list[dict]) -> str:
    items = "".join(f'<li><a href="{esc(safe_url(s.get("url")))}" target="_blank" rel="noopener">{esc(s.get("title") or s.get("url"))}</a></li>'
                    for s in sources if s.get("url"))
    return f'<ol class="ch-src">{items}</ol>' if items else '<p class="ch-src">Aucune source.</p>'


def diff_html(old: str, new: str, why: str = "") -> str:
    o = f'<div class="old">{esc(old) or "<i>(nouveau)</i>"}</div>' if old else '<div class="old"><i>—</i></div>'
    return (f'<div class="ch-diff">{o}<div class="new">{esc(new)}</div></div>'
            + (f'<div class="ch-why">↳ {esc(why)}</div>' if why else ""))


def to_dt(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
    except ValueError:
        return None
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def fmt_dt(s) -> str:
    d = to_dt(s)
    return d.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M") if d else "jamais"


def age_days(s):
    d = to_dt(s)
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400 if d else None


def age_text(s) -> str:
    a = age_days(s)
    return "à une date inconnue" if a is None else "aujourd'hui" if a < 1 else f"il y a {int(a)} j"


def downloads(docx: bytes, pdf: bytes, base: str, key: str):
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Télécharger en Word (.docx)", docx, f"{base}.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"{key}_docx",
                       width="stretch")
    c2.download_button("⬇️ Télécharger en PDF", pdf, f"{base}.pdf", "application/pdf", key=f"{key}_pdf", width="stretch")
