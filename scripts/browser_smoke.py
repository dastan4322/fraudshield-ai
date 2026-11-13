"""Run against local production services; requires playwright and Chromium."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    binary=os.getenv("CHROMIUM_PATH","/usr/bin/chromium")
    browser=p.chromium.launch(**({"executable_path":binary} if binary else {}),args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1440,"height":1100},device_scale_factor=1)
    page.set_default_timeout(60000)
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto(os.getenv("BASE_URL","http://127.0.0.1:3000"),wait_until="domcontentloaded")
    page.get_by_text("200",exact=True).first.wait_for()
    page.get_by_label("Review threshold").fill("0.7")
    page.get_by_text("0.70",exact=True).wait_for()
    page.get_by_label("Search transaction ID").fill("15")
    assert page.locator("tbody tr").count()>0
    page.get_by_label("Search transaction ID").fill("")
    page.get_by_role("button",name="Explain ↗").first.click()
    page.get_by_text("What changed the score?",exact=True).wait_for()
    assert page.locator(".contribution").count()==4
    page.get_by_role("button",name="Overview",exact=True).click()
    Path("docs").mkdir(exist_ok=True)
    page.screenshot(path="docs/dashboard.png",full_page=False)
    page.set_viewport_size({"width":390,"height":844})
    assert page.locator("main").bounding_box()["width"]<=390
    assert not errors, errors
    browser.close()
    print("Browser smoke passed: demo, threshold, filtering, explanation, responsive layout.")
