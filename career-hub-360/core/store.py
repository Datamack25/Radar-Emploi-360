"""Stockage SQLite : offres retenues (avec votre suivi), historique des mises à jour, sites carrières trouvés, liens vérifiés."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

STATUSES = ["Nouvelle", "À postuler", "Postulé", "Entretien", "Refusé", "Ignorée"]
_UNTOUCHED = ("Nouvelle", "Ignorée")
_COLS = ["uid", "source", "dkey", "family", "title", "company", "category", "employeur", "location", "region", "dept",
         "contract", "duration", "salary_min", "salary_max", "experience", "exp_min", "posted_at", "url", "apply_url",
         "description", "logo", "score", "breakdown", "extra", "also"]
_JSON = ("breakdown", "extra", "also")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS offers(uid TEXT PRIMARY KEY, source TEXT, dkey TEXT, family TEXT, title TEXT,
            company TEXT, category TEXT, employeur TEXT, location TEXT, region TEXT, dept TEXT, contract TEXT, duration REAL,
            salary_min INTEGER, salary_max INTEGER, experience TEXT, exp_min INTEGER, posted_at TEXT, url TEXT,
            apply_url TEXT, description TEXT, logo TEXT, score INTEGER, breakdown TEXT, extra TEXT, also TEXT,
            first_run INTEGER, last_run INTEGER, status TEXT DEFAULT 'Nouvelle', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, report TEXT);
        CREATE TABLE IF NOT EXISTS tokens(nom TEXT PRIMARY KEY, ats TEXT, token TEXT, n INTEGER);
        CREATE TABLE IF NOT EXISTS links(site TEXT PRIMARY KEY, ok INTEGER, code TEXT, checked TEXT);
        CREATE TABLE IF NOT EXISTS agent_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, started TEXT, finished TEXT,
            ok INTEGER, summary TEXT);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, kind TEXT, title TEXT,
            company TEXT, offer_uid TEXT, path_docx TEXT, path_pdf TEXT, meta TEXT);
        """)
        self.db.commit()

    # ---------------------------------------------------------- offres
    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        for k in _JSON:
            try:
                d[k] = json.loads(d[k]) if d[k] else ([] if k != "extra" else {})
            except ValueError:
                d[k] = [] if k != "extra" else {}
        return d

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.db.execute("SELECT * FROM offers ORDER BY score DESC, posted_at DESC")]

    def get(self, uid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM offers WHERE uid=?", (uid,)).fetchone()
        return self._row(r) if r else None

    def upsert(self, offers: list[dict], run_id: int) -> None:
        for o in offers:
            vals = [json.dumps(o.get(k), ensure_ascii=False) if k in _JSON else o.get(k) for k in _COLS]
            if self.db.execute("SELECT 1 FROM offers WHERE uid=?", (o["uid"],)).fetchone():
                sets = ", ".join(f"{k}=?" for k in _COLS[1:])
                self.db.execute(f"UPDATE offers SET {sets}, last_run=? WHERE uid=?", vals[1:] + [run_id, o["uid"]])
            else:
                self.db.execute(f"INSERT INTO offers({', '.join(_COLS)}, first_run, last_run) VALUES "
                                f"({', '.join('?' * len(_COLS))}, ?, ?)", vals + [run_id, run_id])
        self.db.commit()

    def expire(self, run_id: int, sources_ok: set) -> int:
        """Retire les offres non suivies qui ont disparu d'une source lue avec succès."""
        if not sources_ok:
            return 0
        q = (f"DELETE FROM offers WHERE last_run < ? AND status IN ({', '.join('?' * len(_UNTOUCHED))}) "
             f"AND source IN ({', '.join('?' * len(sources_ok))})")
        n = self.db.execute(q, [run_id, *_UNTOUCHED, *sorted(sources_ok)]).rowcount
        self.db.commit()
        return n

    def set_user_fields(self, uid: str, status: str, notes: str) -> None:
        self.db.execute("UPDATE offers SET status=?, notes=? WHERE uid=?", (status, notes, uid))
        self.db.commit()

    # ---------------------------------------------------------- mises à jour
    def start_run(self) -> int:
        cur = self.db.execute("INSERT INTO runs(started) VALUES (?)", (_now(),))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, report: dict) -> None:
        self.db.execute("UPDATE runs SET finished=?, report=? WHERE id=?", (_now(), json.dumps(report, ensure_ascii=False), run_id))
        self.db.commit()

    def last_runs(self, n: int = 2) -> list[dict]:
        rows = self.db.execute("SELECT * FROM runs WHERE finished IS NOT NULL ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [{**dict(r), "report": json.loads(r["report"] or "{}")} for r in rows]

    # ---------------------------------------------------------- sites carrières / liens
    def tokens(self) -> dict:
        return {r["nom"]: {"ats": r["ats"], "token": r["token"], "n": r["n"]} for r in self.db.execute("SELECT * FROM tokens")}

    def save_tokens(self, found: dict) -> None:
        for nom, t in found.items():
            self.db.execute("INSERT OR REPLACE INTO tokens VALUES (?,?,?,?)", (nom, t["ats"], t["token"], t.get("n", 0)))
        self.db.commit()

    def delete_token(self, nom: str) -> None:
        self.db.execute("DELETE FROM tokens WHERE nom=?", (nom,))
        self.db.commit()

    def links(self) -> dict:
        return {r["site"]: {"ok": bool(r["ok"]), "code": r["code"]} for r in self.db.execute("SELECT * FROM links")}

    def save_links(self, res: dict) -> None:
        for site, (ok, code) in res.items():
            self.db.execute("INSERT OR REPLACE INTO links VALUES (?,?,?,?)", (site, int(ok), code, _now()))
        self.db.commit()

    # ---------------------------------------------------------- journal des agents
    def log_agent(self, agent: str, started: str, ok: bool, summary: str) -> None:
        self.db.execute("INSERT INTO agent_runs(agent, started, finished, ok, summary) VALUES (?,?,?,?,?)",
                        (agent, started, _now(), int(ok), summary[:500]))
        self.db.commit()

    def last_agent_run(self, agent: str) -> dict | None:
        r = self.db.execute("SELECT * FROM agent_runs WHERE agent=? ORDER BY id DESC LIMIT 1", (agent,)).fetchone()
        return dict(r) if r else None

    def agent_history(self, n: int = 30) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (n,))]

    # ---------------------------------------------------------- documents générés
    def add_document(self, kind: str, title: str, company: str, offer_uid: str | None, path_docx: str, path_pdf: str,
                     meta: dict | None = None) -> None:
        self.db.execute("INSERT INTO documents(created, kind, title, company, offer_uid, path_docx, path_pdf, meta) "
                        "VALUES (?,?,?,?,?,?,?,?)", (_now(), kind, title, company, offer_uid, path_docx, path_pdf,
                                                     json.dumps(meta or {}, ensure_ascii=False)))
        self.db.commit()

    def documents(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM documents ORDER BY id DESC")]

    def delete_document(self, doc_id: int) -> None:
        self.db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        self.db.commit()
