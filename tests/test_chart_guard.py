from catalyst_bot.charts import CHARTS_OK
def test_charts_import_guard_present():
    assert CHARTS_OK in (True, False)
