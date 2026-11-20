"""Playwright browser context manager, action executor, and gate detector."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypedDict, cast

from apply.browser.distiller import EvaluablePage, distill_page
from apply.models import (
    AnswerBankEntry,
    ApplicationStatus,
    DistilledPage,
    FieldActionPlan,
)
from apply.submitters.base import plan_to_dict
from apply.vault import Vault


class PlaybookLike(Protocol):
    def detect_auth_gate(self, url: str, html_content: str) -> str: ...
    def detect_step(self, url: str, html_content: str) -> str: ...


class LocatorLike(Protocol):
    def fill(self, value: str) -> None: ...
    def select_option(self, label: str) -> object: ...
    def check(self) -> None: ...
    def uncheck(self) -> None: ...
    def set_input_files(self, files: str) -> None: ...
    def click(self) -> None: ...


class PageLike(Protocol):
    url: str

    def locator(self, selector: str) -> LocatorLike: ...
    def content(self) -> str: ...
    def screenshot(self, *, path: str, full_page: bool = True) -> bytes: ...


CAPTCHA_MARKERS = (
    "cf-turnstile",
    "challenges.cloudflare.com",
    "g-recaptcha",
    "hcaptcha.com",
    "verify you are human",
)


def detect_bot_gate(html_content: str) -> bool:
    """Return True if the page presents a CAPTCHA / anti-bot challenge."""
    lower = html_content.lower()
    return any(marker in lower for marker in CAPTCHA_MARKERS)


def execute_action_plan(
    page: PageLike,
    plan: FieldActionPlan,
    *,
    execute_submit: bool = False,
) -> list[str]:
    """Execute FieldActionPlan actions on a Playwright page via data-apply-uid."""
    applied: list[str] = []
    for action in plan["field_actions"]:
        uid = action["uid"]
        loc = page.locator(f'[data-apply-uid="{uid}"]')
        act = action["action"]
        val = action["value"]

        if act == "fill_text":
            loc.fill(str(val))
        elif act == "select_option":
            loc.select_option(str(val))
        elif act == "select_typeahead":
            try:
                loc.select_option(str(val))
            except Exception:
                loc.click()
                loc.fill(str(val))
        elif act == "select_radio":
            try:
                page.locator(f'[data-apply-uid="{uid}"] label:has-text("{val}")').click()
            except Exception:
                loc.click()
        elif act == "toggle_checkbox":
            if bool(val):
                loc.check()
            else:
                loc.uncheck()
        elif act == "upload_file":
            loc.set_input_files(str(val))
        elif act == "click":
            loc.click()
        applied.append(uid)

    next_act = plan["next_action"]
    if next_act is not None:
        if not next_act["is_final_submit"] or execute_submit:
            page.locator(f'[data-apply-uid="{next_act["uid"]}"]').click()
            applied.append(next_act["uid"])
    return applied


def serialize_encrypted_storage_state(storage_state: dict[str, object], vault: Vault) -> str:
    """Serialize and encrypt a Playwright storage_state dict."""
    return vault.encrypt(json.dumps(storage_state))


def deserialize_encrypted_storage_state(encrypted_blob: str, vault: Vault) -> dict[str, object]:
    """Decrypt and parse a Playwright storage_state dict."""
    raw = vault.decrypt(encrypted_blob)
    return cast(dict[str, object], json.loads(raw))


def capture_review_screenshot(page: PageLike, output_dir: Path, app_id: int) -> str:
    """Capture a full-page pre-submit screenshot for Copilot review."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"app_{app_id}_review.png"
    page.screenshot(path=str(target), full_page=True)
    return str(target)


class WizardRunResult(TypedDict):
    status: ApplicationStatus
    current_step: str
    filled_payload: dict[str, str]
    screenshot_paths: list[str]
    error_detail: str


def run_playwright_wizard(
    *,
    job_url: str,
    app_id: int,
    playbook: PlaybookLike,
    qa_matcher: Callable[[DistilledPage], dict[str, AnswerBankEntry]],
    planner: Callable[[DistilledPage, dict[str, AnswerBankEntry]], FieldActionPlan],
    vault: Vault,
    encrypted_storage_state: str | None = None,
    copilot_mode: bool = True,
    screenshot_dir: Path = Path(".apply_data/screenshots"),
    max_steps: int = 8,
) -> WizardRunResult:
    """Run a multi-step Playwright distill -> plan -> execute wizard loop."""
    from playwright.sync_api import sync_playwright

    filled_all: dict[str, str] = {}
    screenshots: list[str] = []
    current_step = "init"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        state_tmp: str | None = None
        try:
            if encrypted_storage_state:
                raw_json = vault.decrypt(encrypted_storage_state)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write(raw_json)
                    state_tmp = tf.name
                context = browser.new_context(storage_state=state_tmp)
            else:
                context = browser.new_context()
        except Exception:
            context = browser.new_context()
        finally:
            if state_tmp is not None:
                Path(state_tmp).unlink(missing_ok=True)

        page = context.new_page()
        page.goto(job_url, wait_until="domcontentloaded")

        for _ in range(max_steps):
            html = page.content()
            gate = playbook.detect_auth_gate(page.url, html)
            current_step = playbook.detect_step(page.url, html)

            if gate == "captcha":
                browser.close()
                return {
                    "status": "awaiting_captcha",
                    "current_step": current_step,
                    "filled_payload": filled_all,
                    "screenshot_paths": screenshots,
                    "error_detail": "CAPTCHA / anti-bot gate detected; complete via Live Browser.",
                }
            if gate in ("login_required", "signup_required"):
                browser.close()
                return {
                    "status": "awaiting_auth",
                    "current_step": current_step,
                    "filled_payload": filled_all,
                    "screenshot_paths": screenshots,
                    "error_detail": f"Portal requires authentication ({gate}).",
                }

            distilled = distill_page(
                cast(EvaluablePage, cast(object, page)), detected_step=current_step
            )
            qa_hits = qa_matcher(distilled)
            plan = planner(distilled, qa_hits)
            filled_all.update(plan_to_dict(distilled, plan))

            if plan["missing_info_questions"]:
                browser.close()
                return {
                    "status": "awaiting_user_qa",
                    "current_step": current_step,
                    "filled_payload": filled_all,
                    "screenshot_paths": screenshots,
                    "error_detail": f"{len(plan['missing_info_questions'])} question(s) need user input.",
                }

            execute_action_plan(
                cast(PageLike, cast(object, page)),
                plan,
                execute_submit=not copilot_mode,
            )

            next_act = plan["next_action"]
            if next_act is None:
                break
            if next_act["is_final_submit"] and copilot_mode:
                shot = capture_review_screenshot(
                    cast(PageLike, cast(object, page)), screenshot_dir, app_id
                )
                screenshots.append(shot)
                browser.close()
                return {
                    "status": "ready_for_review",
                    "current_step": current_step,
                    "filled_payload": filled_all,
                    "screenshot_paths": screenshots,
                    "error_detail": "",
                }
            if next_act["is_final_submit"] and not copilot_mode:
                page.wait_for_load_state("domcontentloaded")
                shot = capture_review_screenshot(
                    cast(PageLike, cast(object, page)), screenshot_dir, app_id
                )
                screenshots.append(shot)
                browser.close()
                return {
                    "status": "submitted",
                    "current_step": current_step,
                    "filled_payload": filled_all,
                    "screenshot_paths": screenshots,
                    "error_detail": "",
                }
            page.wait_for_load_state("domcontentloaded")

        browser.close()

    return {
        "status": "ready_for_review" if copilot_mode else "submitted",
        "current_step": current_step,
        "filled_payload": filled_all,
        "screenshot_paths": screenshots,
        "error_detail": "",
    }
