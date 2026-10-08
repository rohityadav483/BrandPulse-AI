from app.services.signals.trends import corroborates


def test_trend_corroboration_requires_directional_change():
    assert corroborates([50, 55, 70])
    assert not corroborates([70, 60, 50])
    assert not corroborates([50, 50])
    assert not corroborates([50])


def test_interest_change_compares_window_means():
    from datetime import date

    from app.services.signals.trends import interest_change_pct

    points = [
        (date(2026, 6, 20), 40),
        (date(2026, 7, 5), 60),  # baseline mean 50
        (date(2026, 7, 15), 60),
        (date(2026, 8, 1), 90),  # current mean 75
        (date(2026, 5, 1), 999),  # outside both windows
    ]
    baseline = (date(2026, 6, 12), date(2026, 7, 11))
    current = (date(2026, 7, 12), date(2026, 8, 10))
    assert interest_change_pct(points, baseline=baseline, current=current) == 50.0


def test_interest_change_is_none_without_both_windows_or_baseline_signal():
    from datetime import date

    from app.services.signals.trends import interest_change_pct

    baseline = (date(2026, 6, 12), date(2026, 7, 11))
    current = (date(2026, 7, 12), date(2026, 8, 10))
    assert interest_change_pct([], baseline=baseline, current=current) is None
    only_current = [(date(2026, 7, 20), 50)]
    assert interest_change_pct(only_current, baseline=baseline, current=current) is None
    zero_base = [(date(2026, 6, 20), 0), (date(2026, 7, 20), 50)]
    assert interest_change_pct(zero_base, baseline=baseline, current=current) is None


def test_trend_corroboration_needs_a_meaningful_rise():
    from app.services.signals.trends import trend_corroborated

    assert trend_corroborated(50.0) and trend_corroborated(10.0)
    assert not trend_corroborated(9.9) and not trend_corroborated(-30.0)
    assert not trend_corroborated(None)
