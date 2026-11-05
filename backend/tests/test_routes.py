from checkweigher.api import routes


def test_live_stream_start_is_timezone_aware():
    # /api/live starts from EPOCH when no weighing is stored yet. A naive epoch needs .astimezone(), which raises
    # OSError on Windows east of UTC (site 1, IST): every tick failed and the dashboard showed "Disconnected".
    assert routes.EPOCH.tzinfo is not None
    assert routes.EPOCH.timestamp() == 0
