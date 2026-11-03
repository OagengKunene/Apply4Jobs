import os
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_browser import serve

from applyatlas.api import create_app
from applyatlas.browser import BrowserExecutor


def test_dashboard_prepares_reviews_and_submits_real_sandbox(tmp_path):
    app = create_app(tmp_path)
    with serve(app) as base:
        # Bind the real sandbox executor to this test server's allocated port.
        app.state.engine.executor = BrowserExecutor(tmp_path, sandbox_base=base)
        token = (tmp_path / "owner-token.txt").read_text()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                                        executable_path=os.getenv("APPLYATLAS_BROWSER_EXECUTABLE") or None)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1120})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                page.get_by_label("Owner access token").fill(token)
                page.get_by_role("button", name="Open workspace").click()
                page.get_by_role("button", name="Load demo").click()
                page.get_by_role("button", name="Run shortlist").click()
                page.get_by_role("button", name="Review application").first.wait_for(timeout=20000)
                if os.getenv("APPLYATLAS_CAPTURE_DOCS") == "true":
                    page.screenshot(path=str(Path(__file__).parents[1] / "docs" / "workspace.png"), full_page=True)
                page.get_by_role("button", name="Review application").first.click()
                page.get_by_role("button", name="Approve & test application").click()
                page.get_by_text("Application received", exact=False).first.wait_for(timeout=30000)
                apps = app.state.store.applications()
                assert any(a["status"] == "submitted" and a["receipt"]["demo"] for a in apps)
                assert app.state.store.verify_chain()
                assert not errors
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-view="overview"]').click()
                assert page.locator("body").evaluate("el => el.scrollWidth <= innerWidth")
                if os.getenv("APPLYATLAS_CAPTURE_DOCS") == "true":
                    page.screenshot(path=str(Path(__file__).parents[1] / "docs" / "mobile.png"), full_page=True)
            finally:
                browser.close()
    app.state.engine.close()
