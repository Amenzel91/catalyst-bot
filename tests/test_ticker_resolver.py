from catalyst_bot.ticker_resolver import _try_from_title, resolve_from_source


def test_try_from_title_basic_patterns():
    assert _try_from_title("Acme Corp (NASDAQ: ABC) announces...") == "ABC"
    assert _try_from_title("Example — NYSE: XYZ completes merger") == "XYZ"
    assert _try_from_title("Company [OTC: ABCD] files 8-K") == "ABCD"
    assert _try_from_title("WidgetCo (Nasdaq: wIdg) to present") == "WIDG"


def test_resolve_from_source_title_win():
    r = resolve_from_source("MegaCo (NYSE American: MEGA) update", None, None)
    assert r.ticker == "MEGA"
    assert r.method == "title"


def test_resolve_from_source_none():
    r = resolve_from_source("No symbol here", None, None)
    assert r.ticker is None
    assert r.method in {"none", "title"}  # title path returns None => "none"
