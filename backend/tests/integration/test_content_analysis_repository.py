"""ContentAnalysisRepository and ItemAspectRepository against a real PostgreSQL (skipped
without TEST_DATABASE_URL). Analyses come from the real `analyze_items` with the stub analyzer;
no model, no SerpApi.

The reuse tests walk the same sequence a pipeline stage will (find stored results by
`(content_hash, analyzer_version)`, copy them, run inference only for what is left) and count
what the analyzer was asked to score.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.repositories.content_analysis import ContentAnalysisRepository
from app.db.repositories.content_item import ContentItemRepository
from app.db.repositories.item_aspect import ItemAspectRepository
from app.schemas.domain import (
    ContentPurpose,
    DateConfidence,
    Sentiment,
    SourceType,
    WindowKind,
)
from app.schemas.nlp import (
    AspectSentiment,
    NewItemAnalysis,
    ReuseTarget,
)
from app.schemas.processing import ContentItem
from app.schemas.serp import SerpEngine
from app.services.nlp.analyzer_version import analyzer_version_for
from app.services.nlp.item_analysis import ItemText, analyze_items
from app.services.nlp.relevance import BrandProfile, detect_relevance
from app.services.nlp.sentiment import StubSentimentAnalyzer

SAMSUNG = BrandProfile("Samsung", products=("Galaxy S25 Ultra",))
TEXTS = {
    "pro": ("Samsung S25 review", "The camera is amazing but battery life is terrible"),
    "price": ("Samsung price", "Great display but expensive"),
    "other": ("Pizza guide", "Best pizza in town"),
}


class CountingAnalyzer(StubSentimentAnalyzer):
    def __init__(self):
        self.calls: list[list[str]] = []

    def analyze(self, texts):
        self.calls.append(list(texts))
        return super().analyze(texts)

    @property
    def scored(self) -> int:
        return sum(len(call) for call in self.calls)


def make_item(key: str, hash_char: str, *, window=WindowKind.current) -> ContentItem:
    title, snippet = TEXTS[key]
    return ContentItem(
        purpose=ContentPurpose.collection,
        window=window,
        source_type=SourceType.news,
        engine=SerpEngine.google_news,
        url=f"https://news.example.test/{key}-{hash_char}",
        url_hash=hash_char * 64,
        domain="news.example.test",
        title=title,
        snippet=snippet,
        date_confidence=DateConfidence.unknown,
        query="samsung",
        content_hash=hash_char * 64,
        collected_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def content(migrated_engine):
    return ContentItemRepository(migrated_engine)


@pytest.fixture
def repo(migrated_engine):
    return ContentAnalysisRepository(migrated_engine)


@pytest.fixture
def aspects_repo(migrated_engine):
    return ItemAspectRepository(migrated_engine)


@pytest.fixture
def brand(new_brand):
    return new_brand()


@pytest.fixture
def analysis(new_analysis, brand):
    return new_analysis(brand)


@pytest.fixture
def stored(content, analysis, brand):
    """Three stored content items: two about Samsung, one not."""
    items = [make_item("pro", "1"), make_item("price", "2"), make_item("other", "3")]
    ids = content.add_many(analysis, brand, items).inserted_ids
    return dict(zip(("pro", "price", "other"), ids, strict=True)), items


def analyze_stored(stored_ids, items, analyzer=None):
    analyzer = analyzer or StubSentimentAnalyzer()
    analyses = analyze_items(
        [ItemText(i.title, i.snippet) for i in items], SAMSUNG, analyzer
    )
    return [
        NewItemAnalysis(content_id=cid, content_hash=item.content_hash, analysis=result)
        for cid, item, result in zip(stored_ids.values(), items, analyses, strict=True)
    ]


# ---- save and read back ----


def test_save_and_read_back_round_trip(repo, stored):
    ids, items = stored
    rows = analyze_stored(ids, items)
    result = repo.save_many(rows)
    assert (result.inserted, result.skipped) == (3, 0)
    assert set(result.inserted_ids) == set(ids.values())

    back = repo.get(ids["pro"])
    expected = rows[0].analysis
    assert back.content_hash == items[0].content_hash and back.analyzed_at is not None
    got = back.analysis
    assert (got.sentiment, got.is_about_brand, got.matched_terms) == (
        expected.sentiment,
        True,
        ("Samsung",),
    )
    assert (
        got.model == expected.model
        and got.analyzer_version == expected.analyzer_version
    )
    assert got.sentiment_score == pytest.approx(expected.sentiment_score, abs=1e-6)
    assert got.negative_prob == pytest.approx(expected.negative_prob, abs=1e-6)
    # keywords/topics (Phase 4.3) must survive the text[] columns unchanged
    assert expected.keywords and expected.topics
    assert (got.topics, got.keywords) == (expected.topics, expected.keywords)
    by_aspect = {a.aspect: a for a in got.aspects}
    assert set(by_aspect) == {"camera", "battery"}
    assert by_aspect["camera"].clause == "The camera is amazing"
    assert by_aspect["camera"].sentiment is Sentiment.positive
    assert by_aspect["battery"].clause == "battery life is terrible"
    assert by_aspect["battery"].sentiment is Sentiment.negative
    assert by_aspect["battery"].score == pytest.approx(-0.7, abs=1e-6)


def test_irrelevant_item_is_stored_neutral_without_aspects(repo, stored):
    ids, items = stored
    repo.save_many(analyze_stored(ids, items))
    other = repo.get(ids["other"]).analysis
    assert not other.is_about_brand and other.sentiment is Sentiment.neutral
    assert other.aspects == () and other.matched_terms == ()


def test_save_is_idempotent_and_never_overwrites(repo, aspects_repo, stored):
    ids, items = stored
    rows = analyze_stored(ids, items)
    repo.save_many(rows)
    again = repo.save_many(rows)
    assert (again.inserted, again.skipped, again.inserted_ids) == (0, 3, ())
    assert len(aspects_repo.list_for_content(ids["pro"])) == 2  # no duplicated aspects

    changed = rows[0].analysis.model_copy(
        update={"sentiment": Sentiment.positive, "aspects": ()}
    )
    result = repo.save_many(
        [
            NewItemAnalysis(
                content_id=ids["pro"],
                content_hash=items[0].content_hash,
                analysis=changed,
            )
        ]
    )
    assert result.inserted == 0
    assert repo.get(ids["pro"]).analysis.sentiment is rows[0].analysis.sentiment
    assert len(aspects_repo.list_for_content(ids["pro"])) == 2


def test_save_empty_is_a_noop(repo):
    assert repo.save_many([]).inserted == 0


def test_save_is_atomic_when_one_content_id_does_not_exist(repo, stored):
    ids, items = stored
    rows = analyze_stored(ids, items)
    ghost = rows[0].model_copy(update={"content_id": uuid.uuid4()})
    with pytest.raises(IntegrityError):
        repo.save_many([rows[1], ghost])
    assert repo.get(ids["price"]) is None  # the valid row was rolled back with it


def test_duplicate_content_id_in_one_call_is_rejected(repo, stored):
    ids, items = stored
    rows = analyze_stored(ids, items)
    with pytest.raises(ValueError):
        repo.save_many([rows[0], rows[0]])


def test_get_many_and_missing(repo, stored):
    ids, items = stored
    repo.save_many(analyze_stored(ids, items)[:2])
    found = repo.get_many([ids["pro"], ids["price"], ids["other"], uuid.uuid4()])
    assert set(found) == {ids["pro"], ids["price"]}
    assert repo.get(ids["other"]) is None
    assert repo.get_many([]) == {}
    assert repo.analyzed_content_ids(ids.values()) == {ids["pro"], ids["price"]}


def test_list_and_count_for_analysis_with_filters(
    repo, stored, analysis, brand, new_analysis
):
    ids, items = stored
    repo.save_many(analyze_stored(ids, items))
    assert repo.count_for_analysis(analysis) == 3
    assert repo.count_for_analysis(analysis, is_about_brand=True) == 2
    assert repo.count_for_analysis(analysis, is_about_brand=False) == 1
    assert repo.count_for_analysis(analysis, brand_id=uuid.uuid4()) == 0
    assert repo.count_for_analysis(new_analysis(brand)) == 0
    listed = repo.list_for_analysis(analysis, brand_id=brand, is_about_brand=True)
    assert [s.content_id for s in listed] == sorted([ids["pro"], ids["price"]])
    assert all(len(s.analysis.aspects) >= 1 for s in listed)


# ---- item_aspects repository ----


def test_aspect_repository_queries(
    repo, aspects_repo, content, stored, analysis, brand
):
    ids, items = stored
    repo.save_many(analyze_stored(ids, items))
    assert [a.aspect for a in aspects_repo.list_for_content(ids["pro"])] == [
        "battery",
        "camera",
    ]
    assert aspects_repo.count(analysis) == 4
    assert aspects_repo.count(analysis, aspect="battery") == 1
    assert (
        aspects_repo.count(analysis, aspect="battery", sentiment=Sentiment.negative)
        == 1
    )
    assert (
        aspects_repo.count(analysis, aspect="battery", sentiment=Sentiment.positive)
        == 0
    )
    assert (
        aspects_repo.count(analysis, sentiment=Sentiment.positive) == 2
    )  # camera, display
    assert aspects_repo.count(analysis, brand_id=uuid.uuid4()) == 0
    assert aspects_repo.count(analysis, window=WindowKind.baseline) == 0
    listed = aspects_repo.list_for_analysis(analysis, aspect="battery")
    assert [(r.content_id, r.aspect.clause) for r in listed] == [
        (ids["pro"], "battery life is terrible")
    ]
    ordered = aspects_repo.list_for_analysis(analysis)
    assert [r.aspect.aspect for r in ordered] == sorted(
        r.aspect.aspect for r in ordered
    )


def test_aspect_repository_window_filter(repo, aspects_repo, content, analysis, brand):
    current = make_item("pro", "4", window=WindowKind.current)
    baseline = make_item("price", "5", window=WindowKind.baseline)
    ids = content.add_many(analysis, brand, [current, baseline]).inserted_ids
    repo.save_many(
        analyze_stored(
            dict(zip(("pro", "price"), ids, strict=True)), [current, baseline]
        )
    )
    assert aspects_repo.count(analysis, window=WindowKind.current) == 2
    assert aspects_repo.count(analysis, window=WindowKind.baseline) == 2
    only = aspects_repo.list_for_analysis(analysis, window=WindowKind.baseline)
    assert {r.content_id for r in only} == {ids[1]}


def test_aspect_repository_add_many_skips_existing_pairs(aspects_repo, stored):
    ids, _ = stored
    battery = AspectSentiment(
        aspect="battery",
        clause="battery drains",
        sentiment=Sentiment.negative,
        negative_prob=0.8,
        score=-0.6,
    )
    camera = battery.model_copy(update={"aspect": "camera", "clause": "camera is fine"})
    assert aspects_repo.add_many(ids["pro"], [battery]) == 1
    assert aspects_repo.add_many(ids["pro"], [battery, camera]) == 1
    assert aspects_repo.add_many(ids["pro"], []) == 0
    assert len(aspects_repo.list_for_content(ids["pro"])) == 2


def test_aspect_rows_need_a_content_item(aspects_repo):
    aspect = AspectSentiment(
        aspect="battery",
        clause="c",
        sentiment=Sentiment.neutral,
        negative_prob=0.1,
        score=0.0,
    )
    with pytest.raises(IntegrityError):
        aspects_repo.add_many(uuid.uuid4(), [aspect])


def test_deleting_the_analysis_removes_nlp_rows(
    repo, aspects_repo, stored, analysis, migrated_engine
):
    ids, items = stored
    repo.save_many(analyze_stored(ids, items))
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    with migrated_engine.connect() as conn:
        for table in ("content_items", "content_analysis", "item_aspects"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


# ---- reuse by (content_hash, analyzer_version) ----


def run_stage(
    repo,
    content,
    analysis,
    brand,
    analyzer,
    profile=SAMSUNG,
    category="consumer_electronics",
):
    """What an analyzing stage will do: skip analyzed items, copy reusable results, run
    inference for the rest. Returns (copied ids, ReuseResult) for assertions."""
    version = analyzer_version_for(analyzer, category)
    items = content.list_for_analysis(analysis, brand_id=brand)
    pending = [
        i for i in items if i.id not in repo.analyzed_content_ids(x.id for x in items)
    ]
    relevant, irrelevant = [], []
    for item in pending:
        (
            relevant
            if detect_relevance(profile, item.title, item.snippet).is_about_brand
            else irrelevant
        ).append(item)

    rows = []
    if irrelevant:  # relevance only, no inference
        analyses = analyze_items(
            [ItemText(i.title, i.snippet) for i in irrelevant],
            profile,
            analyzer,
            category,
        )
        rows += [
            NewItemAnalysis(content_id=i.id, content_hash=i.content_hash, analysis=a)
            for i, a in zip(irrelevant, analyses, strict=True)
        ]

    targets = [
        ReuseTarget(
            content_id=i.id,
            content_hash=i.content_hash,
            matched_terms=detect_relevance(profile, i.title, i.snippet).matched_terms,
        )
        for i in relevant
    ]
    reuse = repo.copy_reusable(targets, version)
    missing = {cid for cid in reuse.missing}
    todo = [i for i in relevant if i.id in missing]
    if todo:
        analyses = analyze_items(
            [ItemText(i.title, i.snippet) for i in todo], profile, analyzer, category
        )
        rows += [
            NewItemAnalysis(content_id=i.id, content_hash=i.content_hash, analysis=a)
            for i, a in zip(todo, analyses, strict=True)
        ]
    repo.save_many(rows)
    return reuse


@pytest.fixture
def second_analysis(new_analysis, brand):
    return new_analysis(brand)


@pytest.fixture
def both(content, analysis, second_analysis, brand):
    """The same three texts collected in two analyses."""
    items = [make_item("pro", "1"), make_item("price", "2"), make_item("other", "3")]
    content.add_many(analysis, brand, items)
    content.add_many(second_analysis, brand, items)
    return items


def comparable(stored):
    a = stored.analysis
    return (
        a.sentiment,
        a.sentiment_score,
        a.negative_prob,
        a.model,
        a.analyzer_version,
        a.aspects,
    )


def test_first_run_scores_and_second_run_of_same_analysis_scores_nothing(
    repo, content, both, analysis, brand
):
    first = CountingAnalyzer()
    reuse = run_stage(repo, content, analysis, brand, first)
    assert first.scored > 0 and len(reuse.missing) == 2 and reuse.reused == ()
    assert repo.count_for_analysis(analysis) == 3

    rerun = CountingAnalyzer()
    run_stage(repo, content, analysis, brand, rerun)
    assert rerun.calls == []  # zero inference on re-run
    assert repo.count_for_analysis(analysis) == 3


def test_same_texts_in_another_analysis_are_copied_with_zero_inference(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    second = CountingAnalyzer()
    reuse = run_stage(repo, content, second_analysis, brand, second)
    assert second.calls == []
    assert len(reuse.reused) == 2 and reuse.missing == ()

    first_rows = {s.content_hash: s for s in repo.list_for_analysis(analysis)}
    second_rows = {s.content_hash: s for s in repo.list_for_analysis(second_analysis)}
    assert set(first_rows) == set(second_rows) and len(second_rows) == 3
    for content_hash, copied in second_rows.items():
        original = first_rows[content_hash]
        assert copied.content_id != original.content_id
        assert comparable(copied) == comparable(original)
        if (
            copied.analysis.is_about_brand
        ):  # copied, not recomputed: keeps when inference ran
            assert copied.analyzed_at == original.analyzed_at
    assert len(repo.get_many([r.content_id for r in second_rows.values()])) == 3


def test_a_different_analyzer_version_is_not_reused(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())

    class Retuned(CountingAnalyzer):
        config_tag = "margin-0.3-len256"

    retuned = Retuned()
    reuse = run_stage(repo, content, second_analysis, brand, retuned)
    assert reuse.reused == () and len(reuse.missing) == 2 and retuned.scored > 0

    renamed = CountingAnalyzer()
    renamed.model_name = "stub-lexicon-v2"
    other_model = run_stage(repo, content, second_analysis, brand, renamed)
    assert (
        other_model.reused == ()
    )  # second_analysis rows already exist -> nothing pending
    assert other_model.already_analyzed == ()


def test_a_different_category_is_not_reused(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    generic = CountingAnalyzer()
    reuse = run_stage(
        repo, content, second_analysis, brand, generic, category="generic"
    )
    assert reuse.reused == () and generic.scored > 0


def test_only_new_texts_are_scored(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    extra = make_item("pro", "6")
    extra = extra.model_copy(
        update={"title": "Samsung new teaser", "snippet": "The screen is stunning"}
    )
    content.add_many(second_analysis, brand, [extra])
    analyzer = CountingAnalyzer()
    reuse = run_stage(repo, content, second_analysis, brand, analyzer)
    assert len(reuse.reused) == 2 and len(reuse.missing) == 1
    assert all("Pizza" not in t for call in analyzer.calls for t in call)
    assert any("stunning" in t for call in analyzer.calls for t in call)
    assert not any(
        "battery life is terrible" in t for call in analyzer.calls for t in call
    )


def test_relevance_is_decided_per_brand_not_copied(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    profile = BrandProfile("Samsung", aliases=("S25",))
    analyzer = CountingAnalyzer()
    run_stage(repo, content, second_analysis, brand, analyzer, profile=profile)
    assert analyzer.calls == []
    copied = {s.content_hash: s for s in repo.list_for_analysis(second_analysis)}
    original = {s.content_hash: s for s in repo.list_for_analysis(analysis)}
    pro = "1" * 64
    assert original[pro].analysis.matched_terms == ("Samsung",)
    assert copied[pro].analysis.matched_terms == (
        "Samsung",
        "S25",
    )  # the caller's own terms
    assert copied[pro].analysis.is_about_brand


def test_a_source_that_was_not_about_its_brand_is_never_reused(
    repo, content, both, analysis, second_analysis, brand
):
    apple = BrandProfile(
        "Apple"
    )  # the Samsung texts are irrelevant to Apple: no inference ran
    quiet = CountingAnalyzer()
    run_stage(repo, content, analysis, brand, quiet, profile=apple)
    assert quiet.calls == []
    assert repo.count_for_analysis(analysis, is_about_brand=False) == 3

    analyzer = CountingAnalyzer()
    reuse = run_stage(repo, content, second_analysis, brand, analyzer)  # Samsung now
    assert reuse.reused == () and len(reuse.missing) == 2 and analyzer.scored > 0
    assert repo.count_for_analysis(second_analysis, is_about_brand=True) == 2


def test_copy_reusable_classifies_every_target(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    version = analyzer_version_for(CountingAnalyzer())
    pro_a = next(
        i for i in content.list_for_analysis(analysis) if i.content_hash == "1" * 64
    )
    pro_b = next(
        i
        for i in content.list_for_analysis(second_analysis)
        if i.content_hash == "1" * 64
    )
    new_b = content.add_many(
        second_analysis, brand, [make_item("price", "7")]
    ).inserted_ids[0]
    targets = [
        ReuseTarget(
            content_id=pro_a.id, content_hash=pro_a.content_hash
        ),  # already analyzed
        ReuseTarget(content_id=pro_b.id, content_hash=pro_b.content_hash),  # reusable
        ReuseTarget(content_id=new_b, content_hash="7" * 64),  # no source
    ]
    result = repo.copy_reusable(targets, version)
    assert result.already_analyzed == (pro_a.id,)
    assert result.reused == (pro_b.id,)
    assert result.missing == (new_b,)
    assert repo.get(new_b) is None
    assert repo.copy_reusable([], version).reused == ()
    again = repo.copy_reusable(targets, version)  # idempotent: nothing is copied twice
    assert again.reused == () and set(again.already_analyzed) == {pro_a.id, pro_b.id}
    assert again.missing == (new_b,)


def test_find_reusable_picks_the_earliest_source_and_filters_version(
    repo, content, both, analysis, second_analysis, brand
):
    run_stage(repo, content, analysis, brand, CountingAnalyzer())
    run_stage(
        repo, content, second_analysis, brand, CountingAnalyzer()
    )  # copies keep analyzed_at
    version = analyzer_version_for(CountingAnalyzer())
    found = repo.find_reusable(["1" * 64, "2" * 64, "3" * 64, "9" * 64], version)
    assert set(found) == {"1" * 64, "2" * 64}  # "3" is not about the brand, "9" unknown
    first_ids = {s.content_hash: s.content_id for s in repo.list_for_analysis(analysis)}
    for content_hash, content_id in found.items():
        assert content_id in {first_ids[content_hash]} | {
            s.content_id for s in repo.list_for_analysis(second_analysis)
        }
    assert repo.find_reusable(["1" * 64], "another|version") == {}
    assert repo.find_reusable([], version) == {}


def test_copy_reusable_rejects_duplicate_targets(repo, stored):
    ids, items = stored
    target = ReuseTarget(content_id=ids["pro"], content_hash=items[0].content_hash)
    with pytest.raises(ValueError):
        repo.copy_reusable([target, target], "v")
