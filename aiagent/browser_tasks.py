"""
Browser automation controller for Hermes Story Video Generation (v2).

Supported actions:
    python -m aiagent.browser_tasks gemini "<prompt>"
    python -m aiagent.browser_tasks gemini_file "<prompt-file>"
    python -m aiagent.browser_tasks gemini_clipboard
    python -m aiagent.browser_tasks status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


GEMINI_URL = "https://gemini.google.com/"
DEFAULT_TIMEOUT_MS = 30_000
GENERATION_TIMEOUT_MS = 180_000


def log(message: str) -> None:
    print(f"[browser_tasks] {message}", file=sys.stderr, flush=True)


class BrowserController:
    def __init__(self, playwright: Playwright):
        self.p = playwright
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.owned_context = False

    def connect(self) -> BrowserContext:
        """
        Attach to existing Chrome first via CDP. If CDP is unavailable, launch a
        persistent browser profile.
        """
        cdp_url = os.environ.get("HERMES_CDP_URL", "").strip()
        if not cdp_url:
            # common default when Chrome was started with --remote-debugging-port=9222
            cdp_url = "http://127.0.0.1:9222"

        if cdp_url:
            try:
                log(f"connecting to existing Chrome via CDP: {cdp_url}")
                self.browser = self.p.chromium.connect_over_cdp(cdp_url)

                contexts = self.browser.contexts
                if not contexts:
                    raise RuntimeError("CDP Chrome has no browser context")

                self.context = contexts[0]
                self.owned_context = False
                log("attached to existing Chrome")
                return self.context
            except Exception as exc:
                log(f"CDP connection failed: {exc}")

        user_data_dir = os.environ.get("HERMES_CHROME_USER_DATA_DIR", "").strip()
        profile = os.environ.get("HERMES_CHROME_PROFILE", "").strip()
        channel = os.environ.get("HERMES_BROWSER_CHANNEL", "").strip() or None

        if not user_data_dir:
            user_data_dir = str(
                Path.home() / "AppData" / "Local" / "HermesChromeProfile"
            )
            log(
                "HERMES_CHROME_USER_DATA_DIR not set; using dedicated persistent "
                f"profile: {user_data_dir}"
            )

        launch_args = {}
        if profile:
            launch_args["args"] = [f"--profile-directory={profile}"]

        log(f"launching persistent browser profile: {user_data_dir}")

        try:
            self.context = self.p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel=channel,
                viewport=None,
                **launch_args,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not launch persistent Chrome profile. "
                "If your normal Chrome is already open, use CDP attachment "
                "(HERMES_CDP_URL or --remote-debugging-port=9222) or close Chrome "
                "before using the profile."
            ) from exc

        self.owned_context = True
        return self.context

    def close(self) -> None:
        if os.environ.get("HERMES_KEEP_BROWSER", "true").lower() in {
            "0", "false", "no"
        }:
            if self.owned_context and self.context:
                try:
                    self.context.close()
                except Exception:
                    pass

    def find_or_create_page(self, url: str) -> Page:
        assert self.context is not None

        for page in self.context.pages:
            try:
                if "gemini.google.com" in page.url:
                    return page
            except Exception:
                pass

        page = self.context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        return page


def wait_for_gemini_input(page: Page) -> Any:
    selectors = [
        "div[contenteditable='true']",
        "textarea",
        "div.ql-editor",
        "[aria-label*='prompt']",
        "[aria-label*='输入']",
    ]

    deadline = time.monotonic() + DEFAULT_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                loc = page.locator(selector).last
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                pass
        time.sleep(0.4)

    raise RuntimeError(
        "Gemini input was not found. The browser may be logged out, "
        "blocked by a consent page, or the Gemini UI may have changed."
    )


def is_login_page(page: Page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return False

    login_markers = [
        "sign in",
        "log in",
        "choose an account",
        "use another account",
        "登录",
        "选择账号",
    ]
    return any(marker in text for marker in login_markers)


def submit_gemini_prompt(page: Page, prompt: str) -> None:
    editor = wait_for_gemini_input(page)
    # Clear any residual content first
    try:
        editor.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
    except Exception:
        pass
    editor.fill(prompt)
    time.sleep(0.3)
    editor.press("Enter")

    time.sleep(0.8)

    send_selectors = [
        'button[aria-label*="Send"]',
        'button[aria-label*="发送"]',
        'button:has-text("Send")',
        'button:has-text("发送")',
        'button[data-test-id*="send"]',
    ]

    for selector in send_selectors:
        try:
            loc = page.locator(selector).last
            if loc.count() and loc.is_visible() and loc.is_enabled():
                loc.click()
                break
        except Exception:
            continue


def response_texts(page: Page) -> list[str]:
    selectors = [
        ".model-response-text",
        "[data-message-author-role='model']",
        "main .markdown",
        "message-content",
        "code",
        "pre",
        "[class*='response']",
    ]

    results: list[str] = []
    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = loc.count()
            for i in range(count):
                try:
                    txt = loc.nth(i).inner_text(timeout=2000).strip()
                    if txt:
                        results.append(txt)
                except Exception:
                    pass
        except Exception:
            pass

    if not results:
        try:
            txt = page.locator("main").inner_text(timeout=2000).strip()
            if txt:
                results.append(txt)
        except Exception:
            pass

    seen = set()
    unique = []
    for txt in results:
        if txt not in seen:
            unique.append(txt)
            seen.add(txt)
    return unique


def extract_json_array(text: str) -> Optional[list[Any]]:
    if not text:
        return None

    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()

    # Fast path
    try:
        value = json.loads(cleaned)
        if isinstance(value, list):
            return value
    except Exception:
        pass

    # Search for the first valid JSON array
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", cleaned):
        start = match.start()
        try:
            value, end = decoder.raw_decode(cleaned[start:])
            if isinstance(value, list):
                return value
        except Exception:
            continue

    return None


def validate_scene_json(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Gemini output is not a JSON array")

    if len(value) != 4:
        raise ValueError(f"Expected 4 scenes, received {len(value)}")

    for index, scene in enumerate(value, start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} is not a JSON object")

    return value


def wait_for_gemini_json(page: Page) -> list[Any]:
    """
    Wait for model response and poll continuously until a valid 4-scene array appears.
    Forces explicit scrolling to trigger rendering of virtualized canvas DOM blocks.
    """
    deadline = time.monotonic() + GENERATION_TIMEOUT_MS / 1000
    last_text = ""

    while time.monotonic() < deadline:
        try:
            # Force virtual DOM rendering by scrolling both window and the last response
            page.evaluate(
                """() => {
                    window.scrollTo(0, document.body.scrollHeight);
                    const responses = document.querySelectorAll(
                        '.model-response-text, [data-message-author-role="model"]'
                    );
                    if (responses.length) {
                        responses[responses.length - 1].scrollIntoView({block: 'end'});
                    }
                }"""
            )
            loc = page.locator(
                ".model-response-text, [data-message-author-role='model']"
            ).last
            if loc.count() > 0:
                loc.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        texts = response_texts(page)

        if texts:
            candidate = texts[-1]
            if candidate != last_text:
                last_text = candidate
                parsed = extract_json_array(candidate)

                if parsed is not None:
                    try:
                        return validate_scene_json(parsed)
                    except ValueError as ve:
                        log(f"JSON candidate rejected: {ve}")

        time.sleep(1.2)

    raise RuntimeError(
        "Gemini did not produce a valid 4-scene JSON array within "
        f"{GENERATION_TIMEOUT_MS // 1000} seconds."
    )


def read_windows_clipboard() -> str:
    commands = [
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
        ],
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
        ],
    ]

    last_error = None
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    return value
            last_error = result.stderr.strip() or f"exit={result.returncode}"
        except Exception as exp:
            last_error = str(exp)

    raise RuntimeError(f"Windows clipboard is empty/unreadable: {last_error}")


def handle_gemini_clipboard() -> str:
    prompt_text = read_windows_clipboard()

    if len(prompt_text) < 400:
        raise RuntimeError(
            f"Clipboard content is too short for the Story prompt "
            f"({len(prompt_text)} chars). Refusing to send. "
            "Make sure 'select_4step' succeeded and the long prompt is on the clipboard."
        )

    log(f"clipboard prompt loaded: {len(prompt_text)} characters")
    return handle_gemini(prompt_text)


def handle_gemini(prompt_text: str) -> str:
    with sync_playwright() as p:
        controller = BrowserController(p)

        try:
            context = controller.connect()
            page = controller.find_or_create_page(GEMINI_URL)

            page.bring_to_front()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)

            page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)

            if is_login_page(page):
                raise RuntimeError(
                    "Gemini appears to be logged out. Use the authenticated "
                    "Chrome profile or attach to the user's existing Chrome "
                    "session via CDP (--remote-debugging-port=9222)."
                )

            wait_for_gemini_input(page)
            submit_gemini_prompt(page, prompt_text)
            scene_json = wait_for_gemini_json(page)

            return json.dumps(
                scene_json,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        finally:
            controller.close()


def read_prompt_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_gemini = sub.add_parser("gemini")
    p_gemini.add_argument("prompt")

    p_file = sub.add_parser("gemini_file")
    p_file.add_argument("path")

    sub.add_parser("gemini_clipboard")
    sub.add_parser("status")

    args = parser.parse_args()

    try:
        if args.action == "gemini":
            print(handle_gemini(args.prompt))
            return 0

        if args.action == "gemini_file":
            print(handle_gemini(read_prompt_file(args.path)))
            return 0

        if args.action == "gemini_clipboard":
            print(handle_gemini_clipboard())
            return 0

        if args.action == "status":
            with sync_playwright() as p:
                controller = BrowserController(p)
                try:
                    controller.connect()
                    print("browser=ready")
                    return 0
                finally:
                    controller.close()

        return 2

    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
