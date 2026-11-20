"""WebSocket CDP screencast bridge for interactive login and CAPTCHA handoff."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.engine import Engine

from apply.browser.runner import serialize_encrypted_storage_state
from apply.db import get_or_create_default_user, upsert_auth_credential
from apply.vault import Vault

log = logging.getLogger("web.screencast")


class CDPSessionLike(Protocol):
    def on(self, event: str, handler: Callable[[dict[str, object]], Awaitable[None]]) -> None: ...

    def send(
        self, method: str, params: dict[str, object] | None = None
    ) -> Awaitable[dict[str, object]]: ...


async def run_cdp_screencast_session(
    websocket: WebSocket,
    *,
    target_url: str,
    domain_key: str,
    board: str,
    engine: Engine,
    vault: Vault,
) -> None:
    """Stream a live Playwright Chromium page via CDP over WebSocket and capture auth."""
    await websocket.accept()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        await websocket.send_json({"type": "error", "message": "Playwright is not installed."})
        await websocket.close()
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        cdp = cast(CDPSessionLike, cast(object, await context.new_cdp_session(page)))

        async def _on_frame(params: dict[str, object]) -> None:
            data = str(params.get("data") or "")
            session_id = params.get("sessionId")
            if data:
                await websocket.send_json({"type": "frame", "data": data})
            if session_id is not None:
                await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})

        cdp.on("Page.screencastFrame", _on_frame)
        await cdp.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": 70, "maxWidth": 1280, "maxHeight": 800},
        )
        await page.goto(target_url, wait_until="domcontentloaded")
        await websocket.send_json({"type": "ready", "url": page.url})

        try:
            while True:
                raw_msg = await websocket.receive_text()
                msg = cast(dict[str, object], json.loads(raw_msg))
                mtype = str(msg.get("type") or "")
                if mtype == "mouse":
                    await cdp.send(
                        "Input.dispatchMouseEvent",
                        {
                            "type": str(msg.get("event") or "mousePressed"),
                            "x": float(str(msg.get("x") or 0)),
                            "y": float(str(msg.get("y") or 0)),
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                elif mtype == "key":
                    text = str(msg.get("text") or "")
                    if text:
                        await cdp.send("Input.insertText", {"text": text})
                elif mtype == "capture_session":
                    state = cast(dict[str, object], await context.storage_state())
                    user = get_or_create_default_user(engine)
                    enc_state = serialize_encrypted_storage_state(state, vault)
                    upsert_auth_credential(
                        engine,
                        user_id=user.id,
                        auth_scope="tenant",
                        domain_key=domain_key,
                        board=board,
                        email_used=str(msg.get("email_used") or user.primary_email),
                        encrypted_password=None,
                        encrypted_storage_state=enc_state,
                        provision_method="user_interactive",
                        status="active",
                    )
                    await websocket.send_json({"type": "captured", "domain_key": domain_key})
                    break
        except WebSocketDisconnect:
            log.info("Screencast WebSocket disconnected for %s", domain_key)
        finally:
            await asyncio.gather(browser.close(), return_exceptions=True)
