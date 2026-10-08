import pytest

from coach import repdb


def example():
    return {
        "exercises": [
            {
                "id": "synthetic-move",
                "name_en": "Synthetic movement",
                "body_part": "upper_legs",
                "equipment": "leg_press",
                "primary_muscles": ["quadriceps"],
                "secondary_muscles": ["hamstrings"],
                "instructions_en": ["Synthetic instruction"],
                "images": {
                    "flat": {
                        "start": "images/flat/synthetic-start.webp",
                        "peak": "images/flat/synthetic-peak.webp",
                    }
                },
            }
        ]
    }


def test_repdb_facts_images_and_credits_remain_source_grounded():
    entry = repdb.convert(example())[0]
    assert entry["id"] == "repdb:synthetic-move"
    assert entry["muscles"] == ["Quads"] and entry["muscles_secondary"] == ["Hamstrings"]
    assert entry["description_language"] == "en"
    assert len(entry["media"]) == 2
    assert all(m["url"].startswith(repdb.ROOT + "images/flat/") for m in entry["media"])
    assert all(m["credit"] == repdb.CREDIT for m in entry["media"])


def test_repdb_rejects_outside_images_and_premium_samples():
    for url in ["https://example.com/tracker.webp", "../private.webp", "premium-samples/move.webp"]:
        data = example()
        data["exercises"][0]["images"]["flat"]["start"] = url
        with pytest.raises(ValueError):
            repdb.convert(data)
