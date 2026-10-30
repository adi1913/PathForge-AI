"""Manual browser smoke test of the whole UI against a RUNNING demo API + built web app.

Not part of the automated suites (needs Playwright + Chromium and two running servers). See README "Running the web app".
Usage:  python3 apps/web/scripts/smoke_browser.py
It registers a fresh account through the UI (Phase 12 auth), so no user id is needed; the API must allow registration.
"""
import re, time, uuid
from playwright.sync_api import sync_playwright

EMAIL = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
PASSWORD = "smoke-test-passphrase-1"
BASE = "http://localhost:3000"
JD = "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n- RAG\n\nPREFERRED QUALIFICATIONS\n- Python\n"
problems, ok = [], []
expected_http = {"on": False, "seen": 0}  # 401/422 console noise is expected only while the negative auth tests run

def check(name, cond, extra=""):
    (ok if cond else problems).append(name + (f" :: {extra}" if extra and not cond else ""))

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    def on_console(m):
        if m.type != "error":
            return
        if expected_http["on"] and re.search(r"status of (401|422)\b", m.text):
            expected_http["seen"] += 1
            return
        problems.append(f"console.{m.type}: {m.text}")
    page.on("console", on_console)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    def on_request_failed(r):
        # Next cancels in-flight link prefetches (?_rsc=) when the page navigates away; that is not a failure.
        if "_rsc=" in r.url and "ERR_ABORTED" in (r.failure or ""):
            return
        problems.append(f"requestfailed: {r.url} {r.failure}")
    page.on("requestfailed", on_request_failed)

    # --- Phase 12 auth flow ---
    page.goto(BASE + "/")
    page.wait_for_url(re.compile(r"/login$"), timeout=10000); check("anonymous visit redirects to /login", True)
    check("no user-id bar anymore", page.get_by_label("Active user id").count() == 0)

    expected_http["on"] = True
    page.get_by_role("button", name="New here? Create an account").click()
    page.get_by_label("Display name (optional)").fill("Smoke Tester")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill("short")
    page.get_by_role("button", name="Create account").click()
    page.locator("p[role=alert]").wait_for(timeout=10000)
    check("weak password rejected with safe message", "password" in page.locator("p[role=alert]").inner_text().lower(),
          page.locator("p[role=alert]").inner_text())
    check("still on /login after failed register", page.url.endswith("/login"))
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.get_by_text(re.compile("Demo mode|Live mode")).wait_for(timeout=15000); check("registered and landed in app", True)
    check("header shows signed-in user", page.get_by_text("Signed in as").first.is_visible())
    page.get_by_text("Roadmap progress").first.wait_for()
    page.get_by_text("No roadmap yet").wait_for(timeout=10000); check("overview empty roadmap", True)
    check("token not in page text", "eyJ" not in page.content())

    page.wait_for_load_state("networkidle")  # let the dashboard finish its fetches before leaving on purpose
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=10000); check("sign out returns to /login", True)
    page.goto(BASE + "/roadmap")
    page.wait_for_url(re.compile(r"/login$"), timeout=10000); check("protected page redirects after sign out", True)

    page.get_by_label("Email").fill(EMAIL); page.get_by_label("Password").fill("wrong-passphrase-123")
    page.get_by_role("button", name="Sign in").click()
    page.locator("p[role=alert]").wait_for(timeout=10000)
    check("wrong password -> generic error", page.locator("p[role=alert]").inner_text().strip() == "Invalid credentials",
          page.locator("p[role=alert]").inner_text())
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text("Signed in as").first.wait_for(timeout=15000); check("login with correct password", True)

    # expired/tampered token: the next API call returns 401, the session is cleared and the user is sent to /login
    page.evaluate("""() => { for (const k of Object.keys(sessionStorage)) {
        const v = sessionStorage.getItem(k); if (v && v.includes('"token"')) {
            const o = JSON.parse(v); o.token = o.token.slice(0, -4) + 'AAAA'; sessionStorage.setItem(k, JSON.stringify(o)); } } }""")
    page.wait_for_load_state("networkidle")
    page.reload()
    page.wait_for_url(re.compile(r"/login$"), timeout=15000); check("tampered token -> redirected to /login", True)
    check("session-expired notice shown", page.get_by_text("session expired", exact=False).count() > 0)
    page.get_by_label("Email").fill(EMAIL); page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text("Signed in as").first.wait_for(timeout=15000); check("re-login after expiry", True)
    expected_http["on"] = False
    check("negative tests produced the expected 401/422 responses", expected_http["seen"] >= 3, str(expected_http["seen"]))

    page.get_by_role("link", name="Job analysis").click()
    page.get_by_label("Job description").fill(JD); page.get_by_role("button", name="Analyze job description").click()
    page.get_by_text("Skill gaps (by priority)").wait_for(timeout=15000)
    check("jd gaps table", page.locator("table tbody tr").count() > 0)
    check("jd gap reasoning", page.locator("table tbody tr").first.inner_text().strip() != "")

    page.get_by_role("link", name="Roadmap").click()
    page.get_by_role("button", name="Generate", exact=True).click()
    page.get_by_role("button", name="Re-plan remaining work").wait_for(timeout=15000)
    page.locator("table tbody tr").first.wait_for(timeout=15000)  # the button mounts before the roadmap data has loaded
    rows = page.locator("table tbody tr").count()
    check("roadmap items", rows > 0, str(rows))
    sel = page.get_by_label(re.compile("^Status for")).first
    sel.select_option("in_progress")
    page.wait_for_timeout(1000)
    check("progress updated", sel.input_value() == "in_progress")
    page.get_by_role("button", name="Re-plan remaining work").click()
    page.get_by_text("Re-planned:").wait_for(timeout=15000)
    check("replan notice", True)

    page.get_by_role("link", name="Assessments").click()
    page.get_by_label("Skill slug").fill("python")
    page.get_by_role("button", name="Generate and start").click()
    page.get_by_role("button", name="Submit answers").wait_for(timeout=15000)
    check("demo label shown", page.get_by_text(re.compile("demo", re.I)).first.is_visible())
    groups = page.locator("fieldset")
    for i in range(groups.count()):
        groups.nth(i).get_by_role("radio").first.check()
    page.get_by_role("button", name="Submit answers").click()
    page.get_by_test_id("confidence").wait_for(timeout=15000)
    txt = page.get_by_test_id("confidence").inner_text()
    check("confidence block", "skill level was not changed" in txt.lower(), txt)
    check("no key words on page", not re.search(r"expected_answer|rubric_keywords|any_of", page.content()))
    page.get_by_text("Evidence history").wait_for()
    check("evidence listed", page.get_by_text(re.compile(r"confidence .* → ")).count() > 0)

    page.get_by_role("link", name="Mentor").click()
    page.get_by_label("Message").fill("What should I learn next?")
    page.get_by_role("button", name="Send").click()
    page.get_by_text("Your next topic").wait_for(timeout=15000)
    check("mentor reply", True)
    page.get_by_label("Message").fill("Explain RAG")
    page.get_by_role("button", name="Send").click()
    page.get_by_text("Missing context:").first.wait_for(timeout=15000)
    check("mentor discloses missing context", True)

    page.get_by_role("link", name="Applications").click()
    page.get_by_label("Job title").fill("ML Engineer"); page.get_by_label("Company").fill("Globex")
    page.get_by_role("button", name="Add").click()
    page.get_by_text("Invalid status jumps").wait_for(timeout=15000)
    check("application created", True)
    page.get_by_role("link", name="GitHub evidence").click()
    page.get_by_label("Repository URL").fill("https://github.com/octocat/hello-world")
    page.get_by_role("button", name="Evaluate").click()
    page.wait_for_timeout(3000)
    check("github shows result or error", page.get_by_text(re.compile("Data source|not|Invalid|error", re.I)).first.is_visible())
    page.get_by_role("link", name="Resume").click()
    page.get_by_label("Resume text").fill("Jane\n\nSKILLS\n- Python\n- Docker\n")
    page.get_by_role("button", name="Analyze resume").click()
    page.get_by_text(re.compile(r"Skills \(\d+\)")).wait_for(timeout=15000)
    check("resume skills", True)
    page.screenshot(path="resume.png")
    b.close()

print("OK:", len(ok)); [print("  +", x) for x in ok]
print("PROBLEMS:", len(problems)); [print("  -", x) for x in problems]
