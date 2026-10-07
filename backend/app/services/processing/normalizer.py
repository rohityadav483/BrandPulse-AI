"""Canonical URL, domain, hashes and comparison keys. Pure functions, no I/O.

Nothing here decides what is a duplicate (that is `dedupe.py`); it only produces the stable
values duplicates are detected on. No third-party dependency: the domain is the host without
presentation prefixes, not a public-suffix registered domain (no PSL available), so two
subdomains of one organisation count as two domains.
"""

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that identify the visitor or campaign, never the page.
_TRACKING_EXACT = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "yclid",
        "_ga",
        "_gl",
        "ref_src",
        "spm",
        "si",
        "feature",
        "ocid",
        "cmpid",
    }
)
_TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "vero_", "hsa_")
_HOST_PREFIXES = ("www.", "m.", "amp.", "mobile.")
_DEFAULT_PORTS = {"http": 80, "https": 443}
_YOUTUBE_HOSTS = frozenset({"youtube.com", "m.youtube.com", "music.youtube.com"})
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def _is_tracking(name: str) -> bool:
    lowered = name.casefold()
    return lowered in _TRACKING_EXACT or lowered.startswith(_TRACKING_PREFIXES)


def _host(parts) -> str | None:
    host = (parts.hostname or "").strip(".").casefold()
    return host or None


def canonical_url(url: str) -> str | None:
    """Stable form of `url`, or None if it is not an http(s) URL with a host.

    Rules: scheme forced to https, host lowercased without `www.`/`m.`/`amp.`/`mobile.`,
    default port and fragment dropped, tracking parameters removed, remaining parameters sorted,
    trailing slash dropped (except the bare root). Path case is kept (paths are case-sensitive).
    `youtu.be/ID` and `youtube.com/watch?v=ID&...` both become `https://youtube.com/watch?v=ID`.
    """
    candidate = url.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        else:
            return None
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.casefold() not in {"http", "https"}:
        return None
    host = _host(parts)
    if host is None:
        return None
    for prefix in _HOST_PREFIXES:
        if host.startswith(prefix) and host.count(".") >= 2:
            host = host[len(prefix) :]
            break
    scheme = parts.scheme.casefold()
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)
    ]
    path = parts.path or "/"

    if host == "youtu.be":
        video = path.strip("/").split("/")[0]
        if video:
            return f"https://youtube.com/watch?v={video}"
    if host in _YOUTUBE_HOSTS or host == "youtube.com":
        if path.rstrip("/") == "/watch":
            video = next((v for k, v in query if k == "v" and v), None)
            if video:
                return f"https://youtube.com/watch?v={video}"
        netloc = "youtube.com"

    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query.sort()
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def extract_domain(url: str) -> str | None:
    """Host of the canonical URL (already lowercased, without `www.`). None for invalid URLs."""
    canonical = canonical_url(url)
    if canonical is None:
        return None
    return urlsplit(canonical).hostname


def url_hash(canonical: str) -> str:
    """sha256 hex of an already-canonical URL."""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_for_match(text: str | None) -> str:
    """Comparison form: NFKC, casefolded, punctuation/symbols/whitespace collapsed to single
    spaces. Never shown to users; two strings that differ only in case, punctuation or spacing
    give the same result."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _NON_WORD.sub(" ", folded).strip()


def content_hash(title: str | None, snippet: str | None) -> str:
    """sha256 hex of the normalized title and snippet (docs/DATABASE.md 5.5). Also the key for
    reusing NLP results by `(content_hash, analyzer_version)`, so it covers exactly the text the
    analyzers see."""
    payload = f"{normalize_for_match(title)}\n{normalize_for_match(snippet)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_TITLE_SEPARATORS = (" - ", " | ", " – ", " — ", " :: ")


def title_key(title: str | None, author: str | None = None) -> str:
    """Normalized title for near-duplicate grouping.

    Syndicated stories often append the outlet ("Headline - Example Daily"). The suffix is
    removed only when it equals the item's own `author` (the outlet), so real subtitles survive.
    """
    text = (title or "").strip()
    outlet = normalize_for_match(author)
    if outlet:
        for separator in _TITLE_SEPARATORS:
            head, sep, tail = text.rpartition(separator)
            if sep and head.strip() and normalize_for_match(tail) == outlet:
                text = head
                break
    return normalize_for_match(text)
