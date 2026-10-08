from coach.gym import planned_logs


def test_multiline_ramp_has_distinct_rows_and_no_invented_loads():
    rows = planned_logs({"sets": 1, "reps": "12\n8\n5", "weight": None})
    assert [s["reps"] for s in rows] == [12, 8, 5]
    assert all(s["weight"] is None and not s["done"] for s in rows)


def test_sparse_history_keeps_series_indices_and_planned_reps():
    rows = planned_logs(
        {"sets": 3, "reps": "10", "weight": None},
        {"sets": [{"weight": 25, "reps": 7, "done": True, "series_index": 1}]},
    )
    assert [s["weight"] for s in rows] == [None, 25, None]
    assert [s["reps"] for s in rows] == [10, 10, 10]
    assert all(not s["done"] for s in rows)


def test_excel_weights_do_not_turn_success_into_actual_reps():
    rows = planned_logs(
        {"sets": 3, "reps": "8–12", "weight": None},
        imported=[{"weights_kg": [5, 5, None]}],
    )
    assert [s["weight"] for s in rows] == [5, 5, None]
    assert all(s["reps"] is None and not s["done"] for s in rows)


def test_ambiguous_and_duration_prescriptions_stay_unknown():
    for raw in ["X", "12/8/5", "10 par côté", "30 s", "max", ""]:
        assert (
            planned_logs({"sets": 3, "reps": raw, "weight": None})
            == [{"weight": None, "reps": None, "seconds": None, "done": False}] * 3
        )
