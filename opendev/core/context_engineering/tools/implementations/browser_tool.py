"""Browser automation tool using Playwright (optional dependency)."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Singleton browser state
_browser_state: dict[str, Any] = {
    "browser": None,
    "context": None,
    "page": None,
}


def _ensure_playwright():
    """Check if playwright is available, raise clear error if not."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _get_page():
    """Get or create the singleton browser page."""
    if _browser_state["page"] is not None:
        try:
            # Check if page is still alive
            _browser_state["page"].title()
            return _browser_state["page"]
        except Exception:
            # Page crashed, reset
            _browser_state["page"] = None
            _browser_state["context"] = None
            _browser_state["browser"] = None

    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) OpenDev-Browser/1.0",
    )
    page = context.new_page()

    _browser_state["_pw"] = pw
    _browser_state["browser"] = browser
    _browser_state["context"] = context
    _browser_state["page"] = page

    return page


def cleanup_browser() -> None:
    """Close the browser and clean up resources."""
    try:
        if _browser_state.get("context"):
            _browser_state["context"].close()
        if _browser_state.get("browser"):
            _browser_state["browser"].close()
        if _browser_state.get("_pw"):
            _browser_state["_pw"].stop()
    except Exception:
        pass
    finally:
        _browser_state["browser"] = None
        _browser_state["context"] = None
        _browser_state["page"] = None


class BrowserTool:
    """Interactive browser automation using Playwright."""

    def __init__(self, default_timeout: int = 10000) -> None:
        self._timeout = default_timeout

    def execute(
        self,
        action: str,
        target: Optional[str] = None,
        value: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute a browser action.

        Args:
            action: Action to perform (navigate, click, type, fill, screenshot,
                   get_text, wait, evaluate, tabs_list, tab_close, back, forward, reload)
            target: Target for the action (URL, CSS selector, JS expression)
            value: Value for the action (text to type, JS to evaluate)
            timeout: Action timeout in ms (default: 10000)

        Returns:
            Result dict with action output and optional screenshot path
        """
        if not _ensure_playwright():
            return {
                "success": False,
                "error": (
                    "Playwright is not installed. Install it with:\n"
                    "  pip install playwright && playwright install chromium"
                ),
                "output": None,
            }

        timeout = timeout or self._timeout

        actions = {
            "navigate": self._navigate,
            "click": self._click,
            "type": self._type,
            "fill": self._fill,
            "screenshot": self._screenshot,
            "get_text": self._get_text,
            "wait": self._wait,
            "evaluate": self._evaluate,
            "tabs_list": self._tabs_list,
            "tab_close": self._tab_close,
            "back": self._back,
            "forward": self._forward,
            "reload": self._reload,
        }

        handler = actions.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown browser action: {action}. Available: {', '.join(actions.keys())}",
                "output": None,
            }

        try:
            return handler(target=target, value=value, timeout=timeout)
        except Exception as e:
            error_msg = str(e)
            # Provide helpful suggestions for common errors
            if "Timeout" in error_msg:
                error_msg += "\nTip: Increase timeout or check if the selector is correct."
            elif "not found" in error_msg.lower() or "no element" in error_msg.lower():
                error_msg += "\nTip: Verify the CSS selector matches an element on the page."
            return {"success": False, "error": error_msg, "output": None}

    def _navigate(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        if not target:
            return {"success": False, "error": "URL is required for navigate", "output": None}
        page = _get_page()
        timeout = kwargs.get("timeout", self._timeout)
        page.goto(target, timeout=timeout, wait_until="domcontentloaded")
        title = page.title()
        return {
            "success": True,
            "output": f"Navigated to: {target}\nTitle: {title}\nURL: {page.url}",
        }

    def _click(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        if not target:
            return {"success": False, "error": "CSS selector is required for click", "output": None}
        page = _get_page()
        timeout = kwargs.get("timeout", self._timeout)
        page.click(target, timeout=timeout)
        return {"success": True, "output": f"Clicked: {target}"}

    def _type(
        self, target: Optional[str] = None, value: Optional[str] = None, **kwargs: Any
    ) -> dict[str, Any]:
        if not target:
            return {"success": False, "error": "CSS selector is required for type", "output": None}
        if value is None:
            return {"success": False, "error": "value (text) is required for type", "output": None}
        page = _get_page()
        timeout = kwargs.get("timeout", self._timeout)
        page.type(target, value, timeout=timeout)
        return {"success": True, "output": f"Typed '{value}' into {target}"}

    def _fill(
        self, target: Optional[str] = None, value: Optional[str] = None, **kwargs: Any
    ) -> dict[str, Any]:
        if not target:
            return {"success": False, "error": "CSS selector is required for fill", "output": None}
        if value is None:
            return {"success": False, "error": "value (text) is required for fill", "output": None}
        page = _get_page()
        timeout = kwargs.get("timeout", self._timeout)
        page.fill(target, value, timeout=timeout)
        return {"success": True, "output": f"Filled {target} with '{value}'"}

    def _screenshot(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        page = _get_page()
        # Save screenshot to temp file
        screenshot_dir = Path(tempfile.gettempdir()) / "opendev-screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        path = screenshot_dir / f"browser_{os.getpid()}.png"

        if target:
            # Screenshot specific element
            element = page.query_selector(target)
            if element:
                element.screenshot(path=str(path))
            else:
                return {"success": False, "error": f"Element not found: {target}", "output": None}
        else:
            page.screenshot(path=str(path), full_page=False)

        return {
            "success": True,
            "output": f"Screenshot saved: {path}\nPage: {page.url}",
            "screenshot_path": str(path),
        }

    def _get_text(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        page = _get_page()
        if target:
            timeout = kwargs.get("timeout", self._timeout)
            element = page.wait_for_selector(target, timeout=timeout)
            if element:
                text = element.text_content() or ""
            else:
                return {"success": False, "error": f"Element not found: {target}", "output": None}
        else:
            text = page.text_content("body") or ""

        # Truncate very long text
        if len(text) > 5000:
            text = text[:5000] + "\n... [truncated]"

        return {"success": True, "output": text}

    def _wait(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        if not target:
            return {"success": False, "error": "CSS selector is required for wait", "output": None}
        page = _get_page()
        timeout = kwargs.get("timeout", self._timeout)
        page.wait_for_selector(target, timeout=timeout)
        return {"success": True, "output": f"Element found: {target}"}

    def _evaluate(
        self, target: Optional[str] = None, value: Optional[str] = None, **kwargs: Any
    ) -> dict[str, Any]:
        js_code = value or target
        if not js_code:
            return {
                "success": False,
                "error": "JavaScript expression is required for evaluate",
                "output": None,
            }
        page = _get_page()
        result = page.evaluate(js_code)
        return {"success": True, "output": str(result) if result is not None else "undefined"}

    def _tabs_list(self, **kwargs: Any) -> dict[str, Any]:
        if not _browser_state.get("context"):
            return {"success": True, "output": "No browser context open", "tabs": []}
        pages = _browser_state["context"].pages
        tabs = []
        for i, p in enumerate(pages):
            tabs.append({"index": i, "url": p.url, "title": p.title()})
        output = "\n".join(f"  [{t['index']}] {t['title']} -- {t['url']}" for t in tabs)
        return {"success": True, "output": f"Open tabs ({len(tabs)}):\n{output}", "tabs": tabs}

    def _tab_close(self, target: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        if not _browser_state.get("context"):
            return {"success": False, "error": "No browser context open", "output": None}
        pages = _browser_state["context"].pages
        try:
            idx = int(target) if target else len(pages) - 1
            if 0 <= idx < len(pages):
                pages[idx].close()
                return {"success": True, "output": f"Closed tab {idx}"}
            return {"success": False, "error": f"Tab index {idx} out of range", "output": None}
        except (ValueError, TypeError):
            return {"success": False, "error": "Tab index must be a number", "output": None}

    def _back(self, **kwargs: Any) -> dict[str, Any]:
        page = _get_page()
        page.go_back()
        return {"success": True, "output": f"Navigated back to: {page.url}"}

    def _forward(self, **kwargs: Any) -> dict[str, Any]:
        page = _get_page()
        page.go_forward()
        return {"success": True, "output": f"Navigated forward to: {page.url}"}

    def _reload(self, **kwargs: Any) -> dict[str, Any]:
        page = _get_page()
        page.reload()
        return {"success": True, "output": f"Reloaded: {page.url}"}
