"""Render the HTML diagrams to PNG:  python docs/diagrams/render.py"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent


def main():
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1800, "height": 1200}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        for name in ("architecture", "flow"):
            page.goto((HERE / f"{name}.html").as_uri())
            page.wait_for_timeout(300)
            page.locator("#stage").screenshot(path=str(OUT / f"{name}.png"))
            print("wrote", OUT / f"{name}.png")
        b.close()
    if errors:
        print("errors:", errors)
        sys.exit(1)


if __name__ == "__main__":
    main()
