<!--
name: 'Tool Description: browser'
description: Interactive browser automation
version: 1.0.0
-->

Interactive browser control for navigating web pages, clicking elements, filling forms, and taking screenshots. Uses a persistent browser session (reused across tool calls).

## Available actions

- navigate(target=url): Navigate to a URL
- click(target=selector): Click an element by CSS selector
- type(target=selector, value=text): Type text character by character
- fill(target=selector, value=text): Fill an input field (clears first)
- screenshot(target=selector?): Take a screenshot (full page or specific element)
- get_text(target=selector?): Extract text content from an element or page
- wait(target=selector): Wait for an element to appear
- evaluate(value=js): Execute JavaScript in the page context
- tabs_list: List open browser tabs
- tab_close(target=index): Close a tab by index
- back/forward/reload: Navigation history

## Requirements

Requires playwright: `pip install playwright && playwright install chromium`

## Usage notes

- The browser instance persists across tool calls within a session
- Use CSS selectors to target elements (e.g., "#login-btn", ".form-input", "button[type=submit]")
- Default timeout is 10 seconds per action
- For SPAs, use wait() after navigate() to ensure content loads
