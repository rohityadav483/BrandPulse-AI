from app.services.signals.trends import corroborates


def test_trend_corroboration_requires_directional_change():
    assert corroborates([50, 55, 70])
    assert not corroborates([70, 60, 50])
    assert not corroborates([50, 50])
    assert not corroborates([50])
