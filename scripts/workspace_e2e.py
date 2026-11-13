"""Authenticated browser workflow against running frontend/API/PostgreSQL.
Requires playwright and Chromium; uses only generated synthetic data.
"""
import json
import os
import secrets
from pathlib import Path
from playwright.sync_api import sync_playwright

base=os.getenv("BASE_URL","http://127.0.0.1:3002")
with sync_playwright() as p:
    binary=os.getenv("CHROMIUM_PATH","/usr/bin/chromium")
    browser=p.chromium.launch(**({"executable_path":binary} if binary else {}),args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1440,"height":1100})
    page.set_default_timeout(60000)
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.goto(base,wait_until="domcontentloaded")
    page.get_by_text("200",exact=True).first.wait_for()
    page.get_by_role("button",name="Next",exact=True).click()
    assert page.get_by_text("Page 2 of 8").is_visible()
    page.get_by_role("button",name="Account workspace",exact=True).click()
    address="browser-"+secrets.token_hex(6)+"@example.test"
    page.get_by_label("Account email").fill(address)
    page.get_by_label("Account password").fill("Browser-test-password-42!")
    page.get_by_role("button",name="Register",exact=True).click()
    page.get_by_role("button",name="Log out",exact=True).wait_for()
    page.get_by_role("button",name="Save investigation",exact=True).click()
    page.get_by_text("investigation: My analysis",exact=True).wait_for()

    rows=page.request.get(base+"/api/demo/transactions").json()["records"]
    import csv,io
    csv_data=io.StringIO()
    writer=csv.DictWriter(csv_data,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    page.get_by_role("button",name="Upload dataset",exact=True).click()
    page.get_by_label("Upload CSV").set_input_files({"name":"synthetic.csv","mimeType":"text/csv","buffer":csv_data.getvalue().encode()})
    page.get_by_text("200 rows",exact=False).first.wait_for()
    page.get_by_role("button",name="Train selected algorithm",exact=True).click()
    page.get_by_text("See the risk. Focus your review.",exact=True).wait_for(timeout=60000)
    page.get_by_role("button",name="Explain ↗").first.click()
    page.get_by_text("Global mean absolute SHAP",exact=True).wait_for(timeout=60000)
    assert page.get_by_text("SHAP summary: contributions by record",exact=True).is_visible()
    page.get_by_role("button",name="Reports",exact=True).click()
    with page.expect_download() as download:
        page.get_by_role("button",name="PDF report",exact=True).click()
    assert download.value.suggested_filename.endswith(".pdf")
    path=Path("/tmp/fraudshield-e2e-report.pdf")
    download.value.save_as(path)
    assert path.read_bytes().startswith(b"%PDF")

    page.get_by_role("button",name="Account workspace",exact=True).click()
    page.get_by_role("button",name="Save report",exact=True).click()
    page.get_by_text("report: My analysis",exact=True).wait_for()
    page.get_by_role("button",name="Log out",exact=True).click()
    page.get_by_label("Account email").fill(address)
    page.get_by_label("Account password").fill("Browser-test-password-42!")
    page.get_by_role("button",name="Log in",exact=True).click()
    page.get_by_role("button",name="Refresh workspace",exact=True).click()
    page.get_by_text("report: My analysis",exact=True).wait_for()
    page.get_by_role("button",name="Open",exact=True).first.click()
    page.get_by_text("See the risk. Focus your review.",exact=True).wait_for()
    page.get_by_text("200",exact=True).first.wait_for()
    page.wait_for_timeout(1800)  # allow the 1500ms Recharts entrance animation to settle
    page.screenshot(path="docs/dashboard.png",full_page=False)
    page.get_by_role("button",name="Account workspace",exact=True).click()
    page.get_by_text("Delete account and all saved data",exact=True).click()
    page.on("dialog",lambda dialog:dialog.accept())
    page.get_by_role("button",name="Permanently delete account",exact=True).click()
    page.get_by_text("Account deleted.",exact=True).wait_for()
    assert not errors,errors
    browser.close()
print("Authenticated browser E2E passed: pagination, registration, save, CSV, train, predict, SHAP, PDF, logout/login, restore, account deletion.")
