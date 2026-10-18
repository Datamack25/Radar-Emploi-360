"""Client HTTP poli : User-Agent identifiable, délai entre requêtes, nouvelles tentatives limitées."""
from __future__ import annotations

import time

import requests


class HttpError(Exception):
    pass


class Http:
    def __init__(self, user_agent: str, delay: float = 0.2, retries: int = 1, timeout: int = 20):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
                               "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6"})
        self.delay, self.retries, self.timeout = delay, retries, timeout
        self._last = 0.0

    def _wait(self):
        dt = time.monotonic() - self._last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last = time.monotonic()

    def request(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        short = url.split("?")[0]
        err = HttpError(f"{short} injoignable")
        for attempt in range(self.retries + 1):
            self._wait()
            try:
                r = self.s.request(method, url, **kw)
            except requests.RequestException as exc:
                err = HttpError(f"{short} injoignable ({type(exc).__name__})")
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                err = HttpError(f"{short} : HTTP {r.status_code}")
                time.sleep(2 * (attempt + 1))
                continue
            return r
        raise err

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def json(self, url: str, **kw):
        r = self.get(url, **kw)
        if r.status_code == 204:
            return None
        if r.status_code >= 400:
            raise HttpError(f"{url.split('?')[0]} : HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise HttpError(f"{url.split('?')[0]} : réponse illisible") from exc
