"""
AgriSaathi Hackathon Judge Acceptance Test Suite
Runs the 16-criterion end-to-end journey against the live application.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.parse
import urllib.request
import uuid
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
BASE_URL = "http://127.0.0.1:8001"


class TestSession:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    def get(self, path: str) -> tuple[int, dict | list | bytes]:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        try:
            with self.opener.open(req) as resp:
                data = resp.read()
                try:
                    return resp.status, json.loads(data.decode())
                except Exception:
                    return resp.status, data
        except urllib.error.HTTPError as err:
            try:
                return err.code, json.loads(err.read().decode())
            except Exception:
                return err.code, {}

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode())

    def post_form(self, path: str, form_data: dict, files: dict | None = None) -> tuple[int, dict]:
        boundary = "----WebKitFormBoundaryAcceptance7MA4YWxkTrZu0gW"
        body = io.BytesIO()
        for key, val in form_data.items():
            body.write(f"--{boundary}\r\n".encode())
            body.write(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            body.write(f"{val}\r\n".encode())
        if files:
            for field_name, (filename, file_bytes, mime) in files.items():
                body.write(f"--{boundary}\r\n".encode())
                body.write(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode())
                body.write(f"Content-Type: {mime}\r\n\r\n".encode())
                body.write(file_bytes)
                body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())
        content_bytes = body.getvalue()

        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=content_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode())


def run_acceptance_journey():
    print("=" * 60)
    print("AGRISATHI FULL ACCEPTANCE TEST — HACKATHON JUDGE JOURNEY")
    print("=" * 60)

    # 1. Health check
    client = TestSession()
    status, health = client.get("/api/v1/health")
    assert status == 200, f"Health check failed: {health}"
    assert health["provider"] == "Google Gemini API"
    assert health["live_gemini_configured"] is True
    print("[PASS] Step 1: Health check passed. Live Gemini configured.")

    # 2. Farmer demo sign-in (Nalgonda 1, Telugu context)
    status, sess = client.post_json("/api/v1/session", {"username": "ramesh", "password": "123"})
    assert status == 200, f"Session failed: {sess}"
    assert sess["identity"]["actor_id"] == "farmer-nalgonda-1"
    print("[PASS] Step 2: Farmer demo session signed in (farmer-nalgonda-1).")

    # 3. Fetch fields and verify Nalgonda Rice
    status, fields = client.get("/api/v1/fields")
    assert status == 200 and len(fields) >= 1
    field = fields[0]
    assert field["district"] == "Nalgonda" and field["crop"] == "Rice"
    print(f"[PASS] Step 3: Field verified: {field['id']} ({field['district']} · {field['crop']}).")

    # 4. Fetch field context and verify Weather, Soil, and Satellite evidence
    status, ctx = client.get(f"/api/v1/fields/{field['id']}/context")
    assert status == 200
    assert ctx["weather"]["status"] == "available", "Weather should be available"
    assert ctx["weather"]["temperature_c"] is not None
    assert ctx["soil"]["status"] == "available", "Soil should be available"
    assert ctx["soil"]["soil_class"].startswith("Red Sandy Loam")
    assert ctx["satellite"]["status"] == "available", "Satellite should be available"
    assert "mean_ndvi" in ctx["satellite"]["metrics"]
    print(f"[PASS] Step 4: Evidence verified (Weather: {ctx['weather']['temperature_c']}°C, Soil: {ctx['soil']['soil_class']}, Satellite NDVI: {ctx['satellite']['metrics']['mean_ndvi']}).")

    # 5. Ask with a crop photo. Sharing it with an officer is a separate opt-in.
    img_byte_arr = io.BytesIO()
    Image.new("RGB", (320, 240), color=(60, 140, 50)).save(img_byte_arr, format="JPEG")
    unique_sub_id = f"judge-acceptance-{uuid.uuid4().hex[:12]}"
    status, case = client.post_form(
        "/api/v1/cases",
        {
            "field_id": field["id"],
            "question": "ఆకులపై పసుపు మచ్చలు వస్తున్నాయి. నేను ఏమి గమనించాలి?",
            "transcript": "ఆకులపై పసుపు మచ్చలు వస్తున్నాయి. నేను ఏమి గమనించాలి?",
            "language": "te",
            "submission_id": unique_sub_id,
        },
        files={"photo": ("leaf.jpg", img_byte_arr.getvalue(), "image/jpeg")},
    )
    assert status == 200, f"Case submission failed: {case}"
    assert case["status"] == "answered"
    assert case["provider"] == "Google Gemini API"
    assert case["advisory"]["live_model_call"] is True
    assert case["photo_shared_with_officer"] is False
    case_id = case["id"]
    print(f"[PASS] Step 5 & 6: Live Gemini Telugu multimodal advisory created: {case_id} (model: {case['model']}).")
    print(f"       Advisory summary: {case['advisory']['summary'][:100]}...")

    # Verify submission idempotency (posting with same submission_id returns the duplicate case)
    status_dup, case_dup = client.post_form(
        "/api/v1/cases",
        {
            "field_id": field["id"],
            "question": "ఆకులపై పసుపు మచ్చలు వస్తున్నాయి. నేను ఏమి గమనించాలి?",
            "submission_id": unique_sub_id,
        },
    )
    assert status_dup == 200 and case_dup["id"] == case_id, "Submission idempotency check failed."

    # Explicit professional-help request: contact and photo are shared only after consent.
    status, contact_case = client.post_form(
        f"/api/v1/cases/{case_id}/contact-officer",
        {
            "expected_version": str(case["version"]),
            "name": "Demo Farmer",
            "phone": "9876501234",
            "location": "Nalgonda, Telangana, Demo Village",
            "query": case["question"],
            "consent": "true",
        },
        files={"photo": ("officer-leaf.jpg", img_byte_arr.getvalue(), "image/jpeg")},
    )
    assert status == 200 and contact_case["status"] == "needs_review"
    assert contact_case["photo_shared_with_officer"] is True
    assert "contact" not in contact_case, "Farmer API response must not expose contact PII."
    assert contact_case["contact_requested"] is True
    print("[PASS] Farmer explicitly requested officer help and consented to share contact/photo details.")

    # 7. Verify uncertainty and cited evidence
    assert case["advisory"]["uncertainty"]
    assert "needs_officer_review" in case["advisory"]
    print("[PASS] Step 7: Uncertainty, cautions, and human review recommendation present.")

    # 8. Switch to Extension Officer
    officer_client = TestSession()
    status, off_sess = officer_client.post_json("/api/v1/session", {"username": "rajesh", "password": "123"})
    assert status == 200
    print("[PASS] Step 8: Extension officer signed in.")

    # 9. Verify case in officer queue
    status, queue = officer_client.get("/api/v1/officer/queue")
    assert status == 200
    matching = next((item for item in queue if item["id"] == case_id), None)
    assert matching is not None, f"Case {case_id} not found in officer queue"
    assert matching["contact"]["name"] == "Demo Farmer"
    assert matching["contact"]["phone"] == "9876501234"
    print(f"[PASS] Step 9: Case {case_id} verified in officer review queue.")

    # 10. Check consented photo retrieval
    status, photo_data = officer_client.get(f"/api/v1/officer/cases/{case_id}/photo")
    assert status == 200 and len(photo_data) > 0
    print("[PASS] Step 10: Officer retrieved consented crop photo securely.")

    # 11. Record human review: approve case
    status, approved = officer_client.post_json(
        f"/api/v1/officer/cases/{case_id}/review",
        {"status": "approved", "note": "Checked rice blast and leaf streak symptoms; advise field confirmation.", "expected_version": contact_case["version"]},
    )
    assert status == 200 and approved["status"] == "approved"
    print(f"[PASS] Step 11: Case {case_id} approved with officer note.")

    # 12. Publish scoped advisory
    status, advisory = officer_client.post_json(
        "/api/v1/officer/advisories",
        {
            "title": "Early leaf yellowing checks in Nalgonda rice",
            "body": "Inspect lower tillers for water stagnation before applying fertilizers. Contact local extension staff for on-site symptom checks.",
            "valid_days": 14,
            "source_case_id": case_id,
        },
    )
    assert status == 200 and advisory["id"].startswith("regional-")
    advisory_id = advisory["id"]
    print(f"[PASS] Step 12: Scoped advisory published: {advisory_id} ('{advisory['title']}').")

    # 13. Privacy contract check: personal contact details rejected
    status, personal_check = officer_client.post_json(
        "/api/v1/officer/advisories",
        {
            "title": "Call officer at 9876543210",
            "body": "Please call +91-9876543210 for help.",
            "valid_days": 7,
            "source_case_id": case_id,
        },
    )
    assert status == 422, "Personal phone number should be rejected"
    print("[PASS] Step 13: Privacy check strictly rejected personal phone number in public advisory.")

    # 14. Regional exchange simulation to Andhra Pradesh / Krishna
    status, exch = officer_client.post_json(f"/api/v1/officer/advisories/{advisory_id}/exchange", {})
    assert status == 200 and exch["status"] == "accepted"
    payload = exch["payload"]
    assert payload["source_state"] == "Telangana"
    assert payload["target_state"] == "Andhra Pradesh"
    assert payload["target_district"] == "Krishna"
    assert "farmer_id" not in payload and "question" not in payload and "photo" not in payload
    print(f"[PASS] Step 14: Advisory transferred via RegionalAdvisoryV1 simulation to Krishna, AP.")
    print("       Privacy contract verified: no farmer PII, question, or photo included in payload.")

    # 15. Verify receiving Krishna farmer sees the advisory in their feed
    krishna_client = TestSession()
    status, _ = krishna_client.post_json("/api/v1/session", {"username": "lakshmi", "password": "123"})
    assert status == 200
    status, k_fields = krishna_client.get("/api/v1/fields")
    k_field = k_fields[0]
    status, feed = krishna_client.get(f"/api/v1/fields/{k_field['id']}/feed")
    assert status == 200 and len(feed) >= 1
    shared_advisory = next((item for item in feed if item["title"] == advisory["title"]), None)
    assert shared_advisory is not None
    assert "Telangana" in shared_advisory["exchange_source"]
    print(f"[PASS] Step 15: Krishna farmer feed received shared advisory: '{shared_advisory['title']}'.")

    # 16. Verify second Telangana district (Khammam) does not get unrelated cross-district feeds
    khammam_client = TestSession()
    khammam_client.post_json("/api/v1/session", {"username": "anil", "password": "123"})
    _, kh_fields = khammam_client.get("/api/v1/fields")
    _, kh_feed = khammam_client.get(f"/api/v1/fields/{kh_fields[0]['id']}/feed")
    assert all(item["title"] != advisory["title"] for item in kh_feed)
    print("[PASS] Step 16: Regional scoping verified: advisory does not leak into Khammam maize feed.")

    print("\n" + "=" * 60)
    print("ALL 16 ACCEPTANCE CRITERIA PASSED WITHOUT COMPROMISE!")
    print("=" * 60)


if __name__ == "__main__":
    run_acceptance_journey()
