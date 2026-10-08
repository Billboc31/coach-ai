import pytest

from coach import activities, activity_series, db


def payload():
    # Synthetic shuffled columns. Factors are Garmin metadata, not universal scaling.
    definitions = [
        ("directPower", "watt", 1),
        ("directTimestamp", "gmt", 0),
        ("directSpeed", "mps", 0.1),
        ("directHeartRate", "bpm", 1),
        ("sumDistance", "meter", 100),
        ("directDoubleCadence", "stepsPerMinute", 1),
        ("directLatitude", "dd", 1),
        ("directElevation", "meter", 100),
    ]
    return {
        "metricDescriptors": [
            {"key": key, "metricsIndex": i, "unit": {"key": unit, "factor": factor}}
            for i, (key, unit, factor) in enumerate(definitions)
        ],
        "activityDetailMetrics": [
            {"metrics": [0, 1000000, 0, 100, 0, 0, 12, -5]},
            {"metrics": [220, 1001000, 3, None, 3, 170, 12, 0]},
            {"metrics": [200, 1002000, 4, 0, 7, 180, 12, 5]},
        ],
        "geoPolylineDTO": {"polyline": "private-location"},
    }


def test_shuffled_descriptor_units_zero_missing_values_and_no_coordinates():
    result = activity_series.decode(payload())
    channels = {c["key"]: c for c in result["channels"]}
    assert result["axes"] == {"time": [0, 1, 2], "distance": [0, 3, 7]}
    assert channels["power"]["values"] == [0, 220, 200]
    assert channels["speed"]["values"] == pytest.approx([0, 10.8, 14.4])
    assert channels["heart_rate"]["values"] == [100, None, None]
    assert channels["run_cadence"]["values"] == [0, 170, 180]
    assert channels["elevation"]["values"] == [-5, 0, 5]
    assert "Latitude" not in str(result) and "private-location" not in str(result)
    assert "1000000" not in str(result)


def test_bad_descriptors_short_samples_unknown_units_and_nonfinite_values():
    raw = payload()
    raw["metricDescriptors"].extend(
        [
            {"key": "directBikeCadence", "metricsIndex": True, "unit": {"key": "rpm"}},
            {"key": "directRunCadence", "metricsIndex": -1, "unit": {"key": "stepsPerMinute"}},
        ]
    )
    raw["metricDescriptors"][2]["unit"]["key"] = "unknown"
    raw["activityDetailMetrics"].append({"metrics": [float("nan"), 1003000]})
    raw["activityDetailMetrics"].append(None)
    result = activity_series.decode(raw)
    assert "speed" in result["unsupported"]
    assert all(c["key"] not in {"speed", "bike_cadence"} for c in result["channels"])
    assert result["channels"][0]["values"][-2:] == [None, None]


def test_elapsed_fallback_does_not_use_active_or_moving_duration():
    raw = payload()
    raw["metricDescriptors"][1].update(key="sumMovingDuration", unit={"key": "second"})
    assert activity_series.decode(raw)["axes"]["time"] == [None, None, None]
    raw["metricDescriptors"][1].update(key="sumElapsedDuration")
    for i, row in enumerate(raw["activityDetailMetrics"]):
        row["metrics"][1] = i * 10
    assert activity_series.decode(raw)["axes"]["time"] == [0, 10, 20]


def test_duplicate_descriptors_and_regressing_axes_are_not_silently_joined():
    raw = payload()
    raw["metricDescriptors"].append(raw["metricDescriptors"][3])
    raw["activityDetailMetrics"][2]["metrics"][1] = 999999
    raw["activityDetailMetrics"][2]["metrics"][4] = 1
    result = activity_series.decode(raw)
    assert not any(c["key"] == "heart_rate" for c in result["channels"])
    assert result["axes"]["time"][-1] is None
    assert result["axes"]["distance"][-1] is None
    with pytest.raises(ValueError):
        activity_series.decode({"activityDetailMetrics": [None] * (activity_series.LIMIT + 1)})


def test_refresh_persists_series_and_later_chart_failure_preserves_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    db.upsert_record("activity", "1", {"activityName": "Synthetic", "duration": 3})

    class Client:
        def login(self, path):
            pass

        def get_activity(self, key):
            return {"summaryDTO": {"averageHR": 100}}

        def get_activity_splits(self, key):
            return {"lapDTOs": []}

        def get_activity_details(self, key, **options):
            return payload()

    monkeypatch.setattr(activities, "Garmin", Client)
    saved = activities.refresh("1")
    assert saved["series"]["count"] == 3
    monkeypatch.setattr(Client, "get_activity_details", lambda *a, **k: [])
    with pytest.raises(activities.DetailUnavailable):
        activities.refresh("1")
    assert activities.details("1") == saved
    monkeypatch.setattr(db, "user_id", lambda: "other")
    assert activities.details("1") is None
