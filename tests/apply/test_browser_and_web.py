"""Tests for Playwright distiller, playbooks, and FastAPI web endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apply.browser.distiller import distill_page
from apply.browser.runner import detect_bot_gate, execute_action_plan
from apply.playbooks.workday import WorkdayPlaybook
from web.app import create_app


class _FakePage:
    def __init__(self, url: str, raw: list[dict[str, object]]) -> None:
        self.url = url
        self._raw = raw

    def evaluate(self, expression: str) -> object:
        assert "data-apply-uid" in expression
        return self._raw


class _FakeLocator:
    def __init__(self, calls: list[tuple[str, str]]) -> None:
        self._calls = calls

    def fill(self, value: str) -> None:
        self._calls.append(("fill", value))

    def select_option(self, label: str) -> object:
        self._calls.append(("select", label))
        return None

    def check(self) -> None:
        self._calls.append(("check", "true"))

    def uncheck(self) -> None:
        self._calls.append(("uncheck", "false"))

    def set_input_files(self, files: str) -> None:
        self._calls.append(("upload", files))

    def click(self) -> None:
        self._calls.append(("click", ""))


class _FakeActionPage:
    def __init__(self) -> None:
        self.url = "https://example.com/apply"
        self.calls: list[tuple[str, str]] = []

    def locator(self, selector: str) -> _FakeLocator:
        self.calls.append(("locator", selector))
        return _FakeLocator(self.calls)

    def content(self) -> str:
        return "<html><body>Apply</body></html>"

    def screenshot(self, *, path: str, full_page: bool = True) -> bytes:
        return b""


def test_distill_and_execute_plan() -> None:
    page = _FakePage(
        "https://cae.wd3.myworkdayjobs.com/apply",
        [
            {
                "uid": "e1",
                "role": "textbox",
                "label": "First Name",
                "required": True,
                "current_value": None,
            },
            {
                "uid": "e2",
                "role": "button",
                "label": "Submit",
                "required": False,
                "current_value": None,
            },
        ],
    )
    distilled = distill_page(page, detected_step="workday:my_information")
    assert distilled["detected_step"] == "workday:my_information"
    assert len(distilled["elements"]) == 2

    act_page = _FakeActionPage()
    applied = execute_action_plan(
        act_page,
        {
            "field_actions": [
                {"uid": "e1", "action": "fill_text", "value": "Alex", "confidence": 0.99}
            ],
            "missing_info_questions": [],
            "next_action": {"uid": "e2", "action": "click", "is_final_submit": True},
        },
        execute_submit=False,
    )
    # Final submit button must NOT be clicked in Copilot dry-run
    assert applied == ["e1"]


def test_workday_playbook_detection() -> None:
    pb = WorkdayPlaybook()
    assert (
        pb.detect_auth_gate("https://x.wd3.myworkdayjobs.com", "<div class='cf-turnstile'></div>")
        == "captcha"
    )
    assert (
        pb.detect_auth_gate(
            "https://x.wd3.myworkdayjobs.com", "Create Account Email Address Verify New Password"
        )
        == "signup_required"
    )
    assert (
        pb.detect_auth_gate("https://x.wd3.myworkdayjobs.com/login", "Sign In Password")
        == "login_required"
    )
    assert (
        pb.detect_step("https://x.wd3.myworkdayjobs.com/apply", "<h1>My Experience</h1>")
        == "workday:my_experience"
    )
    assert detect_bot_gate("Please verify you are human") is True


def test_web_api_profile_settings_and_applications(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'apply_test.db'}"
    app = create_app(apply_db_url=db_url, jobs_db_url=f"sqlite:///{tmp_path / 'missing_jobs.db'}")
    client = TestClient(app)

    res = client.get("/api/profile")
    assert res.status_code == 200
    assert res.json()["settings"]["execution_mode"] == "copilot"

    res_set = client.put(
        "/api/settings",
        json={
            "execution_mode": "copilot",
            "daily_limit": 10,
            "min_match_score": 50.0,
            "auto_create_accounts": True,
            "blocked_companies": [],
            "email_alias_strategy": "plus_address",
            "primary_email": "alex@gmail.com",
            "verification_provider": "manual_prompt",
        },
    )
    assert res_set.status_code == 200
    assert res_set.json()["primary_email"] == "alex@gmail.com"

    res_prep = client.post(
        "/api/applications/prepare",
        json={
            "id": "cae:R1",
            "company": "CAE",
            "title": "Software Engineer",
            "url": "https://cae.wd3.myworkdayjobs.com/en-US/career/job/R1",
            "source": "workday",
            "description": "Python and SQL.",
        },
    )
    assert res_prep.status_code == 200
    app_data = res_prep.json()
    assert app_data["status"] == "awaiting_email_otp"

    res_otp = client.post(
        f"/api/applications/{app_data['id']}/answer",
        json={"otp_code": "654321"},
    )
    assert res_otp.status_code == 200
    assert res_otp.json()["status"] == "ready_for_review"

    res_approve = client.post(f"/api/applications/{app_data['id']}/approve")
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] == "submitted"


def test_email_bridge_extraction() -> None:
    from apply.email_bridge import extract_verification_from_text

    otp, link = extract_verification_from_text(
        "Your Workday verification code is 482910. Or click https://cae.wd3.myworkdayjobs.com/verify?token=abc123"
    )
    assert otp == "482910"
    assert "verify?token=abc123" in link


def test_real_playwright_chromium_wizard(tmp_path: Path) -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from apply.answer_bank import match_page_questions
    from apply.browser.runner import run_playwright_wizard
    from apply.db import create_apply_engine, get_or_create_default_user
    from apply.llm import plan_form_actions
    from apply.models import CandidateProfile
    from apply.vault import Vault

    class _WizardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/step2":
                body = (
                    "<html><body><h1>Review</h1>"
                    "<p>Check your details</p>"
                    "<button type='button'>Submit Application</button>"
                    "</body></html>"
                )
            else:
                body = (
                    "<html><body><h1>My Information</h1>"
                    "<label for='fn'>First Name</label><input id='fn' type='text' required />"
                    "<label for='em'>Email</label><input id='em' type='email' required />"
                    "<button type='button' onclick=\"window.location='/step2'\">Save and Continue</button>"
                    "</body></html>"
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _WizardHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        engine = create_apply_engine("sqlite:///:memory:")
        user = get_or_create_default_user(engine)
        profile: CandidateProfile = {
            "full_name": "Alex Rivera",
            "first_name": "Alex",
            "last_name": "Rivera",
            "email": "alex@example.com",
        }
        res = run_playwright_wizard(
            job_url=f"http://127.0.0.1:{port}/",
            app_id=77,
            playbook=WorkdayPlaybook(),
            qa_matcher=lambda d: match_page_questions(engine, user.id, d),
            planner=lambda d, hits: plan_form_actions(d, profile, hits),
            vault=Vault(key_file=tmp_path / "k.key"),
            copilot_mode=True,
            screenshot_dir=tmp_path / "shots",
        )
        assert res["status"] == "ready_for_review"
        assert res["current_step"] == "workday:review"
        assert res["filled_payload"]["First Name"] == "Alex"
        assert res["filled_payload"]["Email"] == "alex@example.com"
        assert len(res["screenshot_paths"]) == 1
        assert Path(res["screenshot_paths"][0]).is_file()
    finally:
        server.shutdown()


def test_tailor_resume_pdf(tmp_path: Path) -> None:
    from apply.models import CandidateProfile
    from apply.tailor import tailor_resume_for_job

    profile: CandidateProfile = {
        "full_name": "Alex Rivera",
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex@example.com",
        "skills": ["Java", "Python", "FastAPI", "Kubernetes"],
        "work_experience": [
            {
                "company": "Acme",
                "title": "Backend Engineer",
                "start_date": "2022-01",
                "highlights": ["Built Python FastAPI microservices", "Maintained legacy Java"],
            }
        ],
    }
    pdf = tailor_resume_for_job(
        profile,
        job_id="stripe:123",
        job_title="Python Engineer",
        job_description="FastAPI and Kubernetes experience required.",
        output_dir=tmp_path / "tailored",
    )
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF-")


def test_web_imap_settings_and_screenshots(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'apply_imap.db'}"
    app = create_app(apply_db_url=db_url, jobs_db_url=f"sqlite:///{tmp_path / 'none.db'}")
    client = TestClient(app)

    res = client.put(
        "/api/settings",
        json={
            "execution_mode": "copilot",
            "daily_limit": 10,
            "min_match_score": 50.0,
            "auto_create_accounts": True,
            "blocked_companies": [],
            "email_alias_strategy": "plus_address",
            "primary_email": "alex@gmail.com",
            "verification_provider": "imap",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "imap_username": "alex@gmail.com",
            "imap_password": "app-password",
        },
    )
    assert res.status_code == 200
    assert res.json()["has_imap_config"] is True

    prof = client.get("/api/profile").json()
    assert prof["verification_provider"] == "imap"
    assert prof["has_imap_config"] is True

    assert client.get("/api/screenshots/nonexistent.png").status_code == 404


def test_live_websocket_cdp_screencast(tmp_path: Path) -> None:
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _LoginHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Workday Sign In</h1></body></html>")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _LoginHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        db_url = f"sqlite:///{tmp_path / 'apply_ws.db'}"
        app = create_app(apply_db_url=db_url, jobs_db_url=f"sqlite:///{tmp_path / 'none.db'}")
        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/browser/127.0.0.1?url=http://127.0.0.1:{port}/&board=workday"
        ) as ws:
            got_ready = False
            got_frame = False
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("type") == "ready":
                    got_ready = True
                elif msg.get("type") == "frame":
                    got_frame = True
                    break
            assert got_ready is True
            assert got_frame is True
            ws.send_text(json.dumps({"type": "capture_session", "email_used": "alex@gmail.com"}))
            captured = ws.receive_json()
            while captured.get("type") == "frame":
                captured = ws.receive_json()
            assert captured["type"] == "captured"

        creds = client.get("/api/credentials").json()
        assert len(creds) == 1
        assert creds[0]["has_session"] is True
        assert creds[0]["status"] == "active"
    finally:
        server.shutdown()
