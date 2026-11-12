"""Confirmation safety and local persistence integration."""

from __future__ import annotations

import base64
import json
import threading
from datetime import date
from http.client import HTTPConnection
from pathlib import Path

import ezdxf

from plancheck import web
from plancheck.evaluation.plans import corridor_plan
from plancheck.export.dxf import export_dxf
from plancheck.jurisdiction.location_evidence import LocationCandidate, LocationExtraction
from plancheck.jurisdiction.proposal import ProjectSettings, availability, propose
from plancheck.jurisdiction.resolve import AdoptionRecord


def record() -> AdoptionRecord:
    return AdoptionRecord(name="Example Authority", slug="example", level="place", country="IN")


def test_city_never_matches_authority_and_conflicts_are_not_applied() -> None:
    extraction = LocationExtraction(
        source="plan.pdf",
        source_sha256="a" * 64,
        status="ambiguous",
        candidates=[
            LocationCandidate(field="country", value="India", evidence=[]),
            LocationCandidate(field="city", value="Example Authority", evidence=[]),
            LocationCandidate(field="state", value="Maharashtra", evidence=[]),
        ],
        conflicting_fields=["state"],
    )
    result = propose(extraction, [record()])
    assert result.settings.country == "IN"
    assert result.settings.region == ""
    assert result.matched_slugs == []
    assert not result.settings.confirmed
    named = extraction.model_copy(
        update={
            "candidates": [
                LocationCandidate(field="country", value="India", evidence=[]),
                LocationCandidate(
                    field="planning_authority", value="Example Authority", evidence=[]
                ),
            ]
        }
    )
    assert propose(named, [record()]).matched_slugs == ["example"]


def test_unverified_record_remains_not_checked() -> None:
    settings = ProjectSettings(
        country="IN",
        region="Maharashtra",
        authority="Example Authority",
        permit_date=date(2026, 1, 1),
        confirmed=True,
    )
    result = availability(settings, [record()])
    assert result["status"] == "not checked"
    assert not result["adoption_available"]


def test_save_restore_and_settings_change_invalidate_results(tmp_path: Path) -> None:
    previous_store = web.STORE
    web.STORE = tmp_path
    server = web.LocalServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:

        def post(body: dict[str, object], endpoint: str = "/api/save") -> dict[str, object]:
            connection.request(
                "POST", endpoint, json.dumps(body), {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            assert response.status == 200
            result: dict[str, object] = json.loads(response.read())
            return result

        drawing = tmp_path / "site.dxf"
        doc = ezdxf.new()
        doc.modelspace().add_text("Country: India")
        doc.modelspace().add_text("Planning Authority: Example Authority")
        doc.saveas(drawing)
        connection.request(
            "POST",
            "/api/extract",
            json.dumps(
                {"name": "site.dxf", "data": base64.b64encode(drawing.read_bytes()).decode()}
            ),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        extracted = json.loads(response.read())
        assert extracted["proposal"]["settings"]["country"] == "IN"
        assert extracted["extraction"]["candidates"][0]["evidence"][0]["source"] == "site.dxf"
        assert not extracted["proposal"]["settings"]["confirmed"]
        first = post({"name": "Plan", "settings": {"country": "IN"}})
        path = tmp_path / f"{first['id']}.json"
        stored = json.loads(path.read_text())
        stored["requires_new_run"] = False
        path.write_text(json.dumps(stored))
        second = post(
            {
                "id": first["id"],
                "name": "Plan",
                "settings": {"country": "IN", "region": "Maharashtra"},
            }
        )
        assert second["check_results"] is None
        assert second["revision"] == 2
        assert second["requires_new_run"]
        connection.request("GET", "/api/projects")
        assert json.loads(connection.getresponse().read())[0]["settings"]["region"] == "Maharashtra"
        source = export_dxf(corridor_plan(800, 700), tmp_path / "exact.dxf")
        upload = post(
            {"name": source.name, "data": base64.b64encode(source.read_bytes()).decode()},
            "/api/extract",
        )
        settings = {
            "country": "IN",
            "region": "Maharashtra",
            "authority": "Manual authority",
            "permit_date": "2026-01-01",
            "confirmed": True,
            "ada_reference": True,
            "facility_type": "commercial_facility",
            "work_type": "new",
        }
        ready = post({"id": first["id"], "settings": settings, "upload_id": upload["upload_id"]})
        complete = post({"id": first["id"], "revision": ready["revision"]}, "/api/run")
        result = complete["check_results"]
        assert isinstance(result, dict)
        download = f"/api/download/{first['id']}/{result['id']}/report.html"
        connection.request("GET", download)
        response = connection.getresponse()
        assert response.status == 200
        assert "attachment" in str(response.getheader("Content-Disposition"))
        assert b"Local building code: not checked" in response.read()
        post({"id": first["id"], "settings": settings | {"permit_date": "2025-01-01"}})
        connection.request("GET", download)
        response = connection.getresponse()
        assert response.status == 400
        assert b"stale" in response.read()
        connection.request("GET", "/api/projects", headers={"Origin": "https://example.com"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()

    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()
        web.STORE = previous_store
