"""Capture the screenshots used in the README.

Run against a live server:  python scripts/shoot.py
"""

import asyncio
import pathlib

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT = pathlib.Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}


async def login(page):
    await page.goto(BASE, wait_until="networkidle")
    await page.fill('input[name="email"]', "demo@nawa.app")
    await page.fill('input[name="password"]', "nawademo2026")
    await page.click("#auth-submit")
    await page.wait_for_selector("#app:not([hidden])", timeout=15000)
    await page.wait_for_timeout(1200)


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        # 1. Landing / sign-in
        page = await browser.new_page(viewport=DESKTOP)
        await page.goto(BASE, wait_until="networkidle")
        await page.wait_for_timeout(900)
        await page.screenshot(path=OUT / "01-signin.png")
        print("01-signin.png")

        # 2. Studio with the library loaded
        await login(page)
        await page.screenshot(path=OUT / "02-studio.png")
        print("02-studio.png")

        # 3. Open a generation so the transcript and player are visible
        cards = page.locator("#library .gen-card, #library li, #library article")
        if await cards.count() > 0:
            await cards.first.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=OUT / "03-transcript.png")
            print("03-transcript.png")

        # 4. The normaliser preview — the feature that sells the product
        await page.fill("#text", "On 15/11/2026 we raised Rs 1,50,000 from 3 investors.")
        await page.wait_for_timeout(1400)
        await page.screenshot(path=OUT / "04-normaliser.png")
        print("04-normaliser.png")

        # 5. Mobile
        mobile = await browser.new_page(viewport=MOBILE)
        await login(mobile)
        await mobile.screenshot(path=OUT / "05-mobile.png")
        print("05-mobile.png")

        await browser.close()


asyncio.run(main())
