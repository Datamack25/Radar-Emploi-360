"""Sites carrières lus par les API publiques des logiciels de recrutement (Greenhouse, Lever, Ashby,
SmartRecruiters, Workable, Recruitee). Seules ces API publiques, prévues pour être lues, sont utilisées."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .. import geo
from ..filters import title_could_match
from ..http import Http, HttpError
from ..text import html_to_text, norm

PUBLIC_PAGE = {"greenhouse": "https://job-boards.greenhouse.io/{t}", "lever": "https://jobs.lever.co/{t}",
               "ashby": "https://jobs.ashbyhq.com/{t}", "smartrecruiters": "https://jobs.smartrecruiters.com/{t}",
               "workable": "https://apply.workable.com/{t}", "recruitee": "https://{t}.recruitee.com"}


def _o(ats, token, company, sid, title, location, desc, posted, url, apply=None, *, loc_all="", country=None,
       employment="", salary=None, salary_text="", date_incertaine=False):
    return {"source": "ats", "source_id": f"{ats}:{token}:{sid}", "title": title or "", "company": company,
            "location": location or "", "description": desc or "", "posted_at": posted, "url": url,
            "apply_url": apply or url, "logo": None,
            "raw": {"loc_all": loc_all or location, "country": country, "employment": employment or "",
                    "salary": salary, "salary_text": salary_text or ""},
            "extra": {"ats": ats, "employeur": company, "date_incertaine": date_incertaine}}


def _annual(lo, hi, interval: str, currency: str | None):
    if currency and str(currency).upper() not in ("EUR", "€"):
        return None
    f = 1
    it = norm(interval)
    if "month" in it or "mois" in it:
        f = 12
    elif "hour" in it or "heure" in it:
        f = 1607
    lo, hi = (float(lo) * f if lo else None), (float(hi) * f if hi else None)
    if not (lo or hi):
        return None
    return int(lo or hi), int(hi or lo)


def _iso_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat() if ms else None


def greenhouse(http: Http, token: str, company: str, light=False):
    d = http.json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "false" if light else "true"})
    out = []
    for j in (d or {}).get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = " ; ".join(f"{o.get('name', '')} {o.get('location') or ''}" for o in j.get("offices") or [])
        meta = " ".join(str(m.get("value")) for m in j.get("metadata") or [] if m.get("value") and isinstance(m.get("value"), str))
        out.append(_o("greenhouse", token, company, j.get("id"), j.get("title"), loc, html_to_text(j.get("content", "")),
                      j.get("first_published") or j.get("updated_at"), j.get("absolute_url"),
                      loc_all=f"{loc} ; {offices}", employment=meta, date_incertaine=not j.get("first_published")))
    return out


def lever(http: Http, token: str, company: str, light=False):
    data = None
    for host in ("api.lever.co", "api.eu.lever.co"):
        r = http.get(f"https://{host}/v0/postings/{token}", params={"mode": "json"})
        if r.status_code == 200:
            data = r.json()
            break
    if data is None:
        raise HttpError(f"Lever « {token} » introuvable")
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location", "")]
        desc = "\n".join([j.get("descriptionPlain") or ""] +
                         [f"{x.get('text', '')}\n{html_to_text(x.get('content', ''))}" for x in j.get("lists") or []] +
                         [j.get("additionalPlain") or ""])
        sr = j.get("salaryRange") or {}
        out.append(_o("lever", token, company, j.get("id"), j.get("text"), ", ".join(filter(None, locs)), desc,
                      _iso_ms(j.get("createdAt")), j.get("hostedUrl"), j.get("applyUrl"), country=j.get("country"),
                      employment=cat.get("commitment", ""),
                      salary=_annual(sr.get("min"), sr.get("max"), sr.get("interval", ""), sr.get("currency"))))
    return out


def ashby(http: Http, token: str, company: str, light=False):
    d = http.json(f"https://api.ashbyhq.com/posting-api/job-board/{token}", params={"includeCompensation": "true"})
    out = []
    for j in (d or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        addr = (j.get("address") or {}).get("postalAddress") or {}
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(_o("ashby", token, company, j.get("id"), j.get("title"), ", ".join(filter(None, locs)),
                      j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")), j.get("publishedAt"),
                      j.get("jobUrl"), j.get("applyUrl"), country=addr.get("addressCountry"),
                      employment=j.get("employmentType", ""), salary_text=comp))
    return out


def smartrecruiters(http: Http, token: str, company: str, light=False):
    out, offset = [], 0
    for _ in range(5):
        d = http.json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", params={"limit": 100, "offset": offset})
        content = (d or {}).get("content") or []
        for j in content:
            loc = j.get("location") or {}
            country, city = loc.get("country"), loc.get("city", "")
            title = j.get("name", "")
            where = f"{city}, {loc.get('region', '')}"
            desc = ""
            if not light and geo.classify(where, country).status == "fr" and title_could_match(title):
                try:
                    det = http.json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{j['id']}")
                    sec = ((det or {}).get("jobAd") or {}).get("sections") or {}
                    desc = "\n".join(html_to_text((sec.get(k) or {}).get("text", ""))
                                     for k in ("jobDescription", "qualifications", "additionalInformation"))
                except HttpError:
                    pass
            url = f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}"
            emp = " ".join(filter(None, [(j.get("typeOfEmployment") or {}).get("label"), (j.get("experienceLevel") or {}).get("label")]))
            out.append(_o("smartrecruiters", token, (j.get("company") or {}).get("name") or company, j.get("id"), title,
                          where.strip(", "), desc, j.get("releasedDate"), url, country=country, employment=emp))
        offset += len(content)
        if len(content) < 100 or offset >= (d or {}).get("totalFound", 0):
            break
    return out


def workable(http: Http, token: str, company: str, light=False):
    d = http.json(f"https://apply.workable.com/api/v1/widget/accounts/{token}", params={"details": "false" if light else "true"})
    out = []
    for j in (d or {}).get("jobs", []):
        locs = j.get("locations") or [{"city": j.get("city"), "country": j.get("country"), "countryCode": j.get("country_code")}]
        where = " ; ".join(", ".join(filter(None, [x.get("city"), x.get("region"), x.get("country")])) for x in locs)
        codes = {str(x.get("countryCode") or "").upper() for x in locs if x.get("countryCode")}
        country = "FR" if "FR" in codes else (next(iter(codes)) if codes else None)
        url = j.get("url") or f"https://apply.workable.com/{token}/j/{j.get('shortcode')}/"
        out.append(_o("workable", token, company, j.get("shortcode"), j.get("title"), where, html_to_text(j.get("description", "")),
                      j.get("published_on") or j.get("created_at"), url, j.get("application_url"), country=country,
                      employment=j.get("employment_type", "")))
    return out


def recruitee(http: Http, token: str, company: str, light=False):
    d = http.json(f"https://{token}.recruitee.com/api/offers/")
    out = []
    for j in (d or {}).get("offers", []):
        s = j.get("salary") or {}
        out.append(_o("recruitee", token, company, j.get("id"), j.get("title"), j.get("location", ""),
                      html_to_text((j.get("description") or "") + "\n" + (j.get("requirements") or "")),
                      j.get("published_at") or j.get("created_at"), j.get("careers_url"), j.get("careers_apply_url"),
                      country=j.get("country_code"), employment=j.get("employment_type_code", ""),
                      salary=_annual(s.get("min"), s.get("max"), s.get("period", ""), s.get("currency"))))
    return out


PARSERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters,
           "workable": workable, "recruitee": recruitee}


def fetch(targets, http: Http, progress) -> tuple[list[dict], list[str], int]:
    """targets : [(Employer, ats, token)]. Renvoie offres, avertissements, nombre de sites lus avec succès."""
    out, warns, ok = [], [], 0
    for e, ats, token in targets:
        try:
            got = PARSERS[ats](http, token, e.nom)
            for o in got:
                o["company"] = e.nom if ats != "smartrecruiters" else (o["company"] or e.nom)
            out += got
            ok += 1
        except (HttpError, KeyError, ValueError, TypeError) as exc:
            warns.append(f"{e.nom} ({ats}:{token}) : {exc}")
    progress(f"Sites carrières : {ok}/{len(targets)} lus, {len(out)} offres (toutes localisations, avant filtres)")
    return out, warns, ok


# ---------------------------------------------------------------- détection / découverte
_DETECT = [
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9._-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9._%-]+)"),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    ("recruitee", r"//([A-Za-z0-9_-]+)\.recruitee\.com"),
]
_BAD = {"api", "embed", "j", "jobs", "www", "careers", "static", "assets", "v0", "v1", "widget"}


def detect_ats(http: Http, url: str) -> list[dict]:
    r = http.get(url)
    if r.status_code >= 400:
        raise HttpError(f"page inaccessible (HTTP {r.status_code})")
    found = []
    for ats, rx in _DETECT:
        for tok in re.findall(rx, r.text + " " + r.url):
            if tok.lower() not in _BAD and {"ats": ats, "token": tok} not in found:
                found.append({"ats": ats, "token": tok})
    return found


def _slugs(nom: str) -> list[str]:
    n = norm(nom).replace("&", " ")
    n = re.sub(r"\b(sa|sas|group|groupe|france|et cie|cie|co)\b", " ", n)
    words = re.findall(r"[a-z0-9]+", n)
    return list(dict.fromkeys(["".join(words), "-".join(words)])) if words else []


def discover(make_http, employers, progress, workers: int = 8) -> dict:
    """Teste les API publiques pour chaque employeur ; garde un site s'il publie au moins une offre en France."""
    skip = {"Recrutement / intérim", "Régulateur / public"}
    todo = [e for e in employers if not e.token and e.categorie not in skip]

    def one(e):
        http = make_http()
        for s in _slugs(e.nom):
            for ats in PARSERS:
                try:
                    offers = PARSERS[ats](http, s, e.nom, light=True)
                except Exception:  # noqa: BLE001 — jeton inexistant : on passe au suivant
                    continue
                fr = [o for o in offers if geo.classify(o["raw"]["loc_all"], o["raw"]["country"]).status == "fr"]
                if fr:
                    return e.nom, {"ats": ats, "token": s, "n": len(offers)}
        return e.nom, None

    found = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, e) for e in todo]
        for i, f in enumerate(as_completed(futs), 1):
            nom, res = f.result()
            if res:
                found[nom] = res
                progress(f"✅ {nom} : {res['ats']} ({res['n']} offres)")
            if i % 20 == 0:
                progress(f"{i}/{len(todo)} employeurs testés…")
    return found


def check_links(make_http, sites, progress, workers: int = 8) -> dict:
    def one(site):
        http = make_http()
        try:
            r = http.request("HEAD", site, allow_redirects=True)
            if r.status_code in (403, 405) or r.status_code >= 400:
                r = http.get(site, allow_redirects=True)
            return site, (r.status_code < 400, str(r.status_code))
        except HttpError as exc:
            return site, (False, str(exc)[:60])

    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, s) for s in sites]):
            s, v = f.result()
            res[s] = v
    progress(f"{len(res)} liens vérifiés")
    return res
