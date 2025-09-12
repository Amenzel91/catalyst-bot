from catalyst_bot.alerts import enrich_with_indicators


def test_enrich_with_indicators_appends_fields():
    embed = {"title": "t", "fields": []}
    out = enrich_with_indicators(embed, {"vwap": 1.2345, "rsi14": 56.7})
    names = [f["name"] for f in out["fields"]]
    assert "VWAP" in names and "RSI(14)" in names


def test_enrich_with_indicators_noop_on_none():
    e = {"title": "t"}
    assert enrich_with_indicators(e, None) == e
