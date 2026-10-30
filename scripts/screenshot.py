"""Dev helper: screenshot dashboard pages with the locally installed Chrome and report
console errors / slow API calls.

  uv run --with playwright python scripts/screenshot.py http://localhost:5173/ out.png [width] [height]
"""

import sys
import time

from playwright.sync_api import sync_playwright

url, out = sys.argv[1], sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
height = int(sys.argv[4]) if len(sys.argv) > 4 else 1000

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    started: dict[str, float] = {}
    page.on("console", lambda m: m.type in ("error", "warning") and print(f"[console.{m.type}] {m.text}"))
    page.on("pageerror", lambda e: print(f"[pageerror] {e}"))
    page.on("request", lambda r: started.__setitem__(r.url, time.time()))
    page.on(
        "requestfinished",
        lambda r: "/api/" in r.url
        and print(f"[api] {r.response().status if r.response() else '?'} "
                  f"{(time.time() - started.get(r.url, time.time())) * 1000:.0f}ms {r.url.split('/api/')[1][:90]}"),
    )
    page.on("requestfailed", lambda r: print(f"[failed] {r.url} {r.failure}"))
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=out, full_page=True)
    browser.close()
