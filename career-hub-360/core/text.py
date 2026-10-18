"""Outils texte : normalisation (sans accents, minuscules), HTML -> texte."""
from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_FEM = re.compile(r"\((?:e|es|se|ne|ive|euse|rice|le)\)|·e\b")


def norm(s) -> str:
    """Minuscules, sans accents, apostrophes et tirets typographiques unifiés, espaces compactés."""
    s = str(s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("`", "'").replace("–", "-").replace("—", "-").replace("€", " eur ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def norm_title(s) -> str:
    """Intitulé normalisé, sans marques d'écriture inclusive ni H/F."""
    t = _FEM.sub("", norm(s))
    t = re.sub(r"\b[hfm] ?/ ?[hfm]\b|\(h/f\)|\(f/h\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def html_to_text(s) -> str:
    s = str(s or "")
    if "&lt;" in s:
        s = html.unescape(s)
    if "<" in s:
        s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>|</tr>", "\n", s)
        s = re.sub(r"(?i)<li[^>]*>", "• ", s)
        s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()
