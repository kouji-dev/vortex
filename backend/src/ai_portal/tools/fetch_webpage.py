"""fetch_webpage tool — renders a URL with headless Chrome and returns the text content."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "## Webpage Fetching\n"
    "Use the `fetch_webpage` tool to retrieve the full text of a specific URL. "
    "Typical use cases:\n"
    "- A `web_search` returned URLs with promising titles but thin snippets — fetch the best one.\n"
    "- The user asks you to read, summarize, or extract information from a specific link.\n"
    "- You need deeper detail (full article, documentation, stats page) that a snippet cannot provide.\n"
    "You can chain tools: call `web_search` first to find relevant URLs, then `fetch_webpage` "
    "on the most promising result. "
    "If a fetch fails or returns no useful content, try a different URL. "
    "Always synthesize what you fetched into a clear, direct answer for the user."
)

_TIMEOUT = 20_000  # ms
_MAX_CHARS = 8_000


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": (
                "Fetch and read the full text content of a webpage using a real browser. "
                "Handles JavaScript-heavy sites, SPAs, and dynamically loaded content. "
                "Use after web_search when you need more detail than the snippets provide."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the webpage to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    }


def execute(url: str) -> dict:
    try:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                page.goto(url, wait_until="networkidle", timeout=_TIMEOUT)
                page.wait_for_timeout(1500)
                # Dismiss cookie/GDPR consent banners
                page.evaluate("""() => {
                    const acceptPhrases = ['accept all', 'accept & continue', 'agree', 'i accept',
                                           'allow all', 'consent', 'ok', 'got it'];
                    for (const btn of document.querySelectorAll('button, a[role=button]')) {
                        const t = btn.innerText?.toLowerCase().trim() || '';
                        if (acceptPhrases.some(p => t === p || t.startsWith(p))) {
                            btn.click(); break;
                        }
                    }
                }""")
                page.wait_for_timeout(800)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(800)
                text = page.evaluate("""() => {
                    ['script','style','nav','footer','header','aside',
                     '[class*="ad-"]','[id*="advertisement"]',
                     '[class*="cookie"]','[id*="cookie"]',
                     '[class*="consent"]','[id*="consent"]',
                     '[class*="gdpr"]','[id*="gdpr"]'].forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return document.body.innerText || document.body.textContent || '';
                }""")
                content = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
            finally:
                browser.close()

        if not content:
            content = (
                f"The page at {url} returned no readable content. "
                "It may require authentication or block automated access."
            )
        elif len(content) > _MAX_CHARS:
            content = content[:_MAX_CHARS] + "\n\n[content truncated]"

    except Exception as exc:
        logger.warning("fetch_webpage_failed url=%s exc=%s", url, exc)
        content = (
            f"Could not retrieve content from {url}. "
            "The page may use Cloudflare bot protection or require authentication. "
            "Try a different URL or use information from web_search snippets."
        )

    return {"name": "fetch_webpage", "content": content, "_used_kbs": []}
