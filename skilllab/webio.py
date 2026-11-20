"""Web Explorer backend: SSRF-safe fetch + search-provider abstraction.

Every fetched page is untrusted content — extracted text only, never
executed, never treated as instructions.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from urllib.parse import urlparse

import urllib.request

from .lab import LabError

MAX_BYTES = 2_000_000
TIMEOUT = 20
_UA = "SkillLab/0.1 (research reader)"

PRIVATE = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
    "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10", "0.0.0.0/8"))


def _check_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise LabError(f"blocked scheme '{p.scheme or '?'}' — http(s) only")
    if not p.hostname:
        raise LabError("no host in url")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        raise LabError(f"cannot resolve '{p.hostname}'")
    for i in infos:
        addr = ipaddress.ip_address(i[-1][0])
        if any(addr in net for net in PRIVATE):
            raise LabError(f"blocked private/loopback address {addr}")
    return p.hostname


def fetch(url: str, max_bytes: int = MAX_BYTES) -> dict:
    """SSRF-guarded GET. Returns title/text/metadata; raises LabError."""
    _check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            final = r.geturl()
            _check_url(final)          # revalidate after redirects
            ctype = r.headers.get("Content-Type", "")
            raw = r.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise LabError(f"response exceeds {max_bytes} bytes")
    except LabError:
        raise
    except Exception as e:
        raise LabError(f"fetch failed: {e}")
    html = raw.decode("utf-8", "replace")
    title = (re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
             or [None, ""])[1]
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"url": url, "final_url": final, "content_type": ctype,
            "title": title.strip(), "text": text,
            "hash": hashlib.sha256(raw).hexdigest()[:16],
            "bytes": len(raw)}


# ---------------- search providers ----------------
#
# Pluggable: a provider is a callable(query, limit) -> [result dict].
# Configured via lab.yaml `search:` {provider, api_key_env, endpoint}.
# No provider configured = honest error, never fabricated results.


def search(lab, query: str, limit: int = 10) -> list[dict]:
    import os, json
    cfg = lab.cfg.get("search") or {}
    prov = cfg.get("provider")
    if not prov:
        raise LabError("no search provider — set `search.provider` in "
                       "lab.yaml (brave|tavily) + api_key_env")
    key = os.environ.get(cfg.get("api_key_env", ""), "")
    if prov == "brave":
        if not key:
            raise LabError(f"set ${cfg.get('api_key_env')}")
        req = urllib.request.Request(
            "https://api.search.brave.com/res/v1/web/search?"
            + urllib.parse.urlencode({"q": query, "count": limit}),
            headers={"X-Subscription-Token": key,
                     "Accept": "application/json"})
        data = json.loads(urllib.request.urlopen(
            req, timeout=TIMEOUT).read())
        return [{"title": r.get("title"), "url": r.get("url"),
                 "snippet": r.get("description", ""),
                 "provider": "brave", "query": query}
                for r in (data.get("web") or {}).get("results") or []]
    if prov == "tavily":
        if not key:
            raise LabError(f"set ${cfg.get('api_key_env')}")
        body = json.dumps({"api_key": key, "query": query,
                           "max_results": limit}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search", data=body,
            headers={"Content-Type": "application/json"})
        data = json.loads(urllib.request.urlopen(
            req, timeout=TIMEOUT).read())
        return [{"title": r.get("title"), "url": r.get("url"),
                 "snippet": r.get("content", ""),
                 "provider": "tavily", "query": query}
                for r in data.get("results") or []]
    raise LabError(f"unknown search provider '{prov}' "
                   "(brave|tavily supported)")


# ---------------- save to research project ----------------


def save_source(lab, pid: str, fetched: dict,
                excerpt_len: int = 400) -> dict:
    """Persist a fetched page as a project source. Dedupes by final URL
    — re-saving returns the existing record and never clobbers
    annotations. Full extracted text goes to a content-addressed cache
    so the yaml stays Git-friendly."""
    from . import research
    from .models import dump_yaml
    url = fetched["final_url"].rstrip("/").lower()
    for s in research.list_sources(lab, pid):
        if s.url.rstrip("/").lower() == url:
            return {"source": s.model_dump(mode="json"),
                    "deduplicated": True}
    s = research.add_source(
        lab, pid, "url", fetched["title"] or fetched["final_url"],
        url=fetched["final_url"], author="",
        excerpt=fetched["text"][:excerpt_len])
    cache = research.project_dir(lab, pid) / "sources" / "_cache"
    cache.mkdir(exist_ok=True)
    (cache / f"{fetched['hash']}.txt").write_text(fetched["text"])
    return {"source": s.model_dump(mode="json"),
            "content_hash": fetched["hash"],
            "cache": str(cache / f"{fetched['hash']}.txt"),
            "deduplicated": False}


# ---------------- document extraction ----------------


def extract_doc(path: str) -> str:
    """Extract text from .docx (stdlib zip+xml) or .pdf (pypdf).
    md/txt/html are handled by the upload route directly."""
    import zipfile, xml.etree.ElementTree as ET
    p = str(path)
    low = p.lower()
    if low.endswith(".docx"):
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paras = [el.text or "" for el in root.iter(ns + "t")]
        return re.sub(r"\s+", " ", " ".join(paras)).strip()
    if low.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise LabError("PDF needs pypdf — pip install pypdf")
        return "\n".join(pg.extract_text() or ""
                         for pg in PdfReader(p).pages)
    raise LabError(f"unsupported document type: {low.rsplit('.',1)[-1]}")
