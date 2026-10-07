"""cleaner + normalizer: table-driven, pure."""

import pytest

from app.services.processing.cleaner import clean_text
from app.services.processing.normalizer import (
    canonical_url,
    content_hash,
    extract_domain,
    normalize_for_match,
    title_key,
    url_hash,
)

# ---------- cleaner ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   \n\t ", None),
        ("<p></p>", None),
        ("\u200b\u200d", None),
        ("plain", "plain"),
        ("  padded  text \n here ", "padded text here"),
        ("<b>Bold</b> and <a href='x'>link</a>", "Bold and link"),
        ("Tom &amp; Jerry &lt;3", "Tom & Jerry <3"),
        ("non\u00a0breaking\u2009thin", "non breaking thin"),
        ("zero\u200bwidth\ufeff", "zerowidth"),
        ("line1\r\nline2\x00", "line1 line2"),
        ("Café", "Café"),
        ("Cafe\u0301", "Café"),  # NFC
        ("a < b and c > d", "a < b and c > d"),  # not a tag
    ],
)
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


def test_clean_text_keeps_case_and_punctuation():
    assert clean_text("  S25 ULTRA: Battery?!  ") == "S25 ULTRA: Battery?!"


def test_clean_text_is_idempotent():
    once = clean_text(" <i>x</i>&amp;  y ")
    assert clean_text(once) == once


# ---------- canonical_url / domain ----------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.test/a", "https://example.test/a"),
        ("HTTP://Example.TEST/a", "https://example.test/a"),
        ("https://www.example.test/a", "https://example.test/a"),
        ("https://m.example.test/a", "https://example.test/a"),
        ("https://amp.example.test/a", "https://example.test/a"),
        ("https://example.test/a/", "https://example.test/a"),
        ("https://example.test/", "https://example.test/"),
        ("https://example.test", "https://example.test/"),
        ("https://example.test/a#section", "https://example.test/a"),
        ("https://example.test:443/a", "https://example.test/a"),
        ("http://example.test:80/a", "https://example.test/a"),
        ("https://example.test:8443/a", "https://example.test:8443/a"),
        ("https://example.test/A/B", "https://example.test/A/B"),  # path case kept
        ("https://example.test/a?utm_source=x&utm_medium=y", "https://example.test/a"),
        ("https://example.test/a?id=2&utm_campaign=c&gclid=z", "https://example.test/a?id=2"),
        ("https://example.test/a?b=2&a=1", "https://example.test/a?a=1&b=2"),
        ("https://example.test/a?q=", "https://example.test/a?q="),
        ("  https://example.test/a  ", "https://example.test/a"),
        ("//cdn.example.test/x", "https://cdn.example.test/x"),
        ("https://youtu.be/abc123?si=zzz", "https://youtube.com/watch?v=abc123"),
        (
            "https://www.youtube.com/watch?v=abc123&feature=share",
            "https://youtube.com/watch?v=abc123",
        ),
        ("https://m.youtube.com/watch?v=abc123&t=5", "https://youtube.com/watch?v=abc123"),
        (
            "https://www.youtube.example.test/watch?v=mock0001",
            "https://youtube.example.test/watch?v=mock0001",
        ),
    ],
)
def test_canonical_url(url, expected):
    assert canonical_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "example.test/a",
        "ftp://example.test/a",
        "mailto:a@b.test",
        "javascript:alert(1)",
        "https://",
        "https:///path",
        "https://example.test:99999/a",
    ],
)
def test_canonical_url_rejects_non_http_urls(url):
    assert canonical_url(url) is None
    assert extract_domain(url) is None


def test_canonical_url_is_idempotent():
    once = canonical_url("HTTPS://WWW.Example.test/A/?utm_source=x&b=2&a=1#f")
    assert canonical_url(once) == once


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://www.Example.test/a", "example.test"),
        ("https://news.example.test/a", "news.example.test"),  # no public-suffix list
        ("https://example.test:8443/a", "example.test"),
        ("https://youtu.be/abc", "youtube.com"),
    ],
)
def test_extract_domain(url, domain):
    assert extract_domain(url) == domain


def test_url_hash_is_stable_sha256_of_the_canonical_url():
    canonical = "https://example.test/a"
    assert url_hash(canonical) == url_hash(canonical)
    assert len(url_hash(canonical)) == 64
    assert url_hash(canonical) != url_hash("https://example.test/b")
    # tracking-only differences hash identically once canonicalised
    a = url_hash(canonical_url("https://www.example.test/a/?utm_source=x"))
    assert a == url_hash(canonical)


# ---------- normalize_for_match / content_hash / title_key ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  Hello,   WORLD!! ", "hello world"),
        ("S25-Ultra: battery's drain", "s25 ultra battery s drain"),
        ("ＦＵＬＬ width", "full width"),  # NFKC
        ("Straße", "strasse"),  # casefold
        ("!!!", ""),
    ],
)
def test_normalize_for_match(raw, expected):
    assert normalize_for_match(raw) == expected


def test_content_hash_ignores_case_punctuation_and_spacing():
    a = content_hash("Galaxy S25 Ultra: Battery drain!", "Users  report problems.")
    b = content_hash("galaxy s25 ultra battery drain", "users report problems")
    assert a == b and len(a) == 64


def test_content_hash_distinguishes_different_text_and_field_boundaries():
    assert content_hash("a", "b c") != content_hash("a b", "c")
    assert content_hash("title", "one") != content_hash("title", "two")
    assert content_hash("title", None) == content_hash("title", "")
    assert content_hash("title", None) != content_hash("title", "snippet")


@pytest.mark.parametrize(
    ("title", "author", "expected"),
    [
        ("Samsung S25 battery - Example Daily", "Example Daily", "samsung s25 battery"),
        ("Samsung S25 battery | Example Daily", "example daily", "samsung s25 battery"),
        ("Samsung S25 battery – Example Daily", "Example Daily", "samsung s25 battery"),
        (
            "Samsung S25 battery - A real subtitle",
            "Example Daily",
            "samsung s25 battery a real subtitle",
        ),
        ("Samsung S25 battery - Example Daily", None, "samsung s25 battery example daily"),
        ("Samsung S25 battery", "Example Daily", "samsung s25 battery"),
        (None, None, ""),
    ],
)
def test_title_key(title, author, expected):
    assert title_key(title, author) == expected
