"""Synthetic import regressions. Never store a real user's workbook here."""

import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from test_gym import workbook_bytes

from coach import api, gym
from coach.secrets import write_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    write_secret(tmp_path / "app.json", {"access_key": "synthetic-test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as value:
        assert (
            value.post("/api/login", json={"access_key": "synthetic-test-key"}).status_code == 200
        )
        yield value


def upload(client, binary, filename="example.xlsx"):
    return client.post(
        "/api/gym/import",
        json={"filename": filename, "base64": base64.b64encode(binary).decode()},
    )


def with_last_cell(reference, content=""):
    original = io.BytesIO(workbook_bytes())
    result = io.BytesIO()
    row = "".join(c for c in reference if c.isdigit())
    with (
        zipfile.ZipFile(original) as source,
        zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                cell = f'<row r="{row}"><c r="{reference}" s="0"{content}</c></row>'
                data = data.replace(b"</sheetData>", cell.encode() + b"</sheetData>")
            target.writestr(entry.filename, data)
    return result.getvalue()


def test_real_data_bounds_ignore_far_away_empty_formatting(client):
    binary = with_last_cell("XFD1048576", ">")
    assert len(binary) < 10000
    response = upload(client, binary)
    assert response.status_code == 200
    assert len(response.json()["sheets"][0]["rows"]) == 8
    assert response.json()["sheets"][0]["mapping"]["name"] == 3


def test_small_workbook_structure_error_is_not_a_five_mb_error(client):
    binary = with_last_cell("A1001", ' t="n"><v>1</v>')
    response = upload(client, binary)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "1001" in detail and "1000 lignes" in detail
    assert "5 Mo" not in detail


def test_valid_workbook_around_606_kib_is_accepted(client):
    binary = io.BytesIO(workbook_bytes())
    with zipfile.ZipFile(binary, "a", zipfile.ZIP_STORED) as archive:
        archive.writestr("customXml/item1.xml", "<data>" + " " * (606 * 1024) + "</data>")
    assert 600 * 1024 < len(binary.getvalue()) < 650 * 1024
    assert upload(client, binary.getvalue()).status_code == 200


def test_size_and_decompressed_size_have_distinct_diagnoses(client, monkeypatch):
    monkeypatch.setattr(gym, "MAX_FILE", 1024)
    too_large = upload(client, workbook_bytes())
    assert too_large.status_code == 413 and "5 Mo" in too_large.json()["detail"]
    monkeypatch.setattr(gym, "MAX_FILE", 5 * 1024 * 1024)
    monkeypatch.setattr(gym, "MAX_UNCOMPRESSED", 1024)
    inflated = upload(client, workbook_bytes())
    assert inflated.status_code == 422
    assert "décompressé" in inflated.json()["detail"] and "5 Mo" not in inflated.json()["detail"]


def test_format_and_payload_errors_keep_accurate_messages(client):
    old = upload(client, b"not-xlsx", "example.xls")
    assert old.status_code == 422 and "convertir" in old.json()["detail"]
    broken = upload(client, b"not-xlsx")
    assert broken.status_code == 422 and "invalide" in broken.json()["detail"]
    assert "5 Mo" not in broken.json()["detail"]
    malformed = client.post("/api/gym/import", json=[])
    assert malformed.status_code == 422 and "Requête" in malformed.json()["detail"]
