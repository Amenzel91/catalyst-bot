from catalyst_bot.feeds import dedupe
def test_dedupe_stable():
    items = [{"id":"a"},{"id":"a"},{"id":"b"}]
    out = dedupe(items)
    assert len(out) == 2
