from app.services.scoring.health import compute_health
from app.services.signals.detector import detect_negative_spike
from app.services.signals.metrics import MetricItem, compute_window_metrics


def row(window, source, sentiment="neutral", neg=0.1, aspect="battery", growth=True):
    return MetricItem(window, source, aspect, sentiment, neg, True, growth)


def test_window_metrics_growth_frequency_cross_source_and_sentiment():
    rows = [row("current", "web", "negative", 0.6) for _ in range(5)]
    rows += [row("current", "news", "negative", 0.8) for _ in range(2)]
    rows += [row("current", "youtube", "negative", 0.7) for _ in range(2)]
    rows += [row("current", "forum") for _ in range(11)]
    rows += [row("baseline", "web", "negative", 0.5) for _ in range(1)]
    rows += [row("baseline", "news") for _ in range(19)]
    m = compute_window_metrics(rows, "battery")
    assert m.current_n == 7 and m.current_total == 7
    assert m.baseline_n == 1 and m.baseline_total == 20
    assert m.current_share == 1.0
    assert m.cross_source == 0.75
    assert round(m.sentiment_impact, 3) == 0.667


def test_metrics_empty_and_missing_baseline_are_safe():
    m = compute_window_metrics([], "battery")
    assert m.growth is None and m.frequency == 0 and m.cross_source == 0


def test_detector_enforces_guards():
    rows = [row("current", "web", "negative", 0.8) for _ in range(2)]
    rows += [row("baseline", "web") for _ in range(20)]
    assert detect_negative_spike(rows, "battery") is None


def test_detector_planted_spike_is_high():
    rows = [row("current", "web", "negative", 0.8) for _ in range(9)]
    rows += [row("current", "news", "negative", 0.7) for _ in range(3)]
    rows += [row("current", "youtube", "negative", 0.6) for _ in range(3)]
    rows += [row("current", "forum") for _ in range(5)]
    rows += [row("baseline", "web", "negative", 0.5) for _ in range(2)]
    rows += [row("baseline", "news") for _ in range(25)]
    signal = detect_negative_spike(rows, "battery", trend_corroborated=True)
    assert signal is not None
    assert signal.kind == "aspect_negative_spike"
    assert signal.impact == "high"
    assert round(signal.score, 2) >= 0.75


def test_health_is_deterministic_and_bounded():
    h = compute_health(
        positive_pct=62,
        negative_pct=17,
        current_sample=64,
        baseline_sample=41,
        interest_change_pct=31,
    )
    assert 0 <= h.overall <= 100
    assert h.formula_version == "v1"
    assert (
        compute_health(
            positive_pct=62,
            negative_pct=17,
            current_sample=64,
            baseline_sample=41,
            interest_change_pct=31,
        )
        == h
    )
