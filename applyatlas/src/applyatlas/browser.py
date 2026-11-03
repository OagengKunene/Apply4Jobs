from __future__ import annotations

import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright

from .documents import resume_pdf
from .models import now
from .policy import SUPPORTED_HOSTS

# Form labels are interpreted by a small allowlist, never as executable prompts.
FIELD_MAP = {
    "first_name": [r"^first name\b"], "last_name": [r"^last name\b"],
    "name": [r"^(full |legal )?name\b"], "email": [r"^e.?mail\b"],
    "phone": [r"^(phone|mobile|telephone)\b"],
    "cover_letter": [r"^cover letter\b", r"^additional information\b"],
    "location": [r"^(current )?(location|city)\b"], "resume": [r"^(resume|cv)\b"],
}
POST_HOSTS = SUPPORTED_HOSTS | {"boards-api.greenhouse.io", "api.lever.co", "api.eu.lever.co"}


def field_key(label):
    for key, patterns in FIELD_MAP.items():
        if any(re.search(pattern, label.strip(), re.I) for pattern in patterns):
            return key
    return None


def public_host(host):
    try:
        addresses = socket.getaddrinfo(host, None)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (OSError, ValueError):
        return False


class BrowserExecutor:
    """A bounded observe/plan/act/verify executor for known hosted ATS forms.

    Unknown required questions, consents, sign-in and CAPTCHAs stop execution.
    Unknown submission outcomes are never retried automatically.
    """

    def __init__(self, data_dir: Path, sandbox_base=None):
        self.data_dir = data_dir
        self.sandbox_base = sandbox_base

    def execute(self, job, candidate, packet, app_id):
        if job.source == "demo":
            if not self.sandbox_base:
                return {"status": "needs_attention", "reason": "Sandbox server is not configured"}
            url = self.sandbox_base + "/sandbox/apply/" + app_id
        else:
            if os.getenv("APPLYATLAS_LIVE_SUBMIT", "false").lower() != "true":
                return {"status": "needs_attention", "reason": "Live submission is disabled by server configuration"}
            url = job.url
            if urlsplit(url).hostname not in SUPPORTED_HOSTS:
                return {"status": "needs_attention", "reason": "Unsupported ATS host"}
        try:
            return self._apply(url, job.source == "demo", candidate, packet)
        except Exception as exc:
            # Avoid leaking contact fields or page content in exception messages.
            return {"status": "needs_attention", "reason": f"Browser interrupted ({type(exc).__name__}); "
                    "check the employer portal before any retry", "uncertain": True}

    def _apply(self, url, sandbox, candidate, packet):
        parts = candidate.name.split(maxsplit=1)
        values = {"name": candidate.name, "first_name": parts[0],
                  "last_name": parts[1] if len(parts) > 1 else "", "email": candidate.email,
                  "phone": candidate.phone, "location": candidate.location,
                  "cover_letter": packet["cover_letter"]}
        pdf_bytes = resume_pdf(packet)
        allowed_sandbox_origin = urlsplit(self.sandbox_base) if sandbox else None
        dns_cache = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                                        executable_path=os.getenv("APPLYATLAS_BROWSER_EXECUTABLE") or None)
            try:
                context = browser.new_context(accept_downloads=False, service_workers="block")

                def guard(route):
                    request = route.request
                    parsed = urlsplit(request.url)
                    if sandbox:
                        safe = (parsed.scheme, parsed.netloc) == (allowed_sandbox_origin.scheme,
                                                                allowed_sandbox_origin.netloc)
                    else:
                        host = parsed.hostname
                        if parsed.scheme not in {"https", "data", "blob"}:
                            route.abort()
                            return
                        if parsed.scheme in {"data", "blob"}:
                            route.continue_()
                            return
                        if host not in dns_cache:
                            dns_cache[host] = public_host(host)
                        safe = dns_cache[host]
                        if request.is_navigation_request() and request.frame == page.main_frame:
                            safe = safe and host in SUPPORTED_HOSTS
                        if request.method not in {"GET", "HEAD", "OPTIONS"}:
                            safe = safe and host in POST_HOSTS
                    route.continue_() if safe else route.abort()

                context.route("**/*", guard)
                page = context.new_page()
                page.set_default_timeout(10000)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if not sandbox and urlsplit(page.url).hostname not in SUPPORTED_HOSTS:
                    return {"status": "needs_attention", "reason": "Unexpected navigation"}
                # Some Greenhouse views expose the form after an explicit Apply action.
                if page.locator("input[type=email]").count() == 0:
                    apply = page.get_by_role("button", name=re.compile(r"^apply( now| for this job)?$", re.I))
                    if apply.count() == 1 and apply.is_visible():
                        apply.click()
                visible = page.locator("body").inner_text()
                if re.search(r"verify (you are|you're) human|sign in to apply|log in to apply|enter.*verification code",
                             visible, re.I):
                    return {"status": "needs_attention", "reason": "Authentication or human verification required"}
                for iframe in page.locator("iframe").all():
                    src = iframe.get_attribute("src") or ""
                    if re.search("recaptcha|hcaptcha|challenges.cloudflare", src, re.I) and iframe.is_visible():
                        return {"status": "needs_attention", "reason": "CAPTCHA requires the client"}

                fields = page.locator("input:not([type=hidden]), textarea, select").all()
                plan = []
                blockers = []
                for field in fields:
                    if not field.is_visible() or not field.is_enabled():
                        continue
                    meta = field.evaluate("""el => ({tag:el.tagName.toLowerCase(),type:el.type,
                      required:el.required || el.getAttribute('aria-required') === 'true',
                      label:Array.from(el.labels||[]).map(l=>l.innerText).join(' ') ||
                        el.getAttribute('aria-label') || el.placeholder || el.name || '',value:el.value})""")
                    if meta["type"] in {"submit", "button", "reset"}:
                        continue
                    key = field_key(meta["label"])
                    if meta["type"] in {"checkbox", "radio"} or meta["tag"] == "select":
                        if meta["required"]:
                            blockers.append(meta["label"] or "Required choice")
                        continue
                    if not key:
                        if meta["required"]:
                            blockers.append(meta["label"] or "Unmapped required field")
                        continue
                    if key == "resume" and meta["type"] != "file":
                        if meta["required"]:
                            blockers.append("Unrecognised resume widget")
                        continue
                    if key != "resume" and not values.get(key):
                        if meta["required"]:
                            blockers.append("Missing verified " + key)
                        continue
                    plan.append((field, key))
                if blockers:
                    return {"status": "needs_attention", "reason": "Client answers or consent required",
                            "unanswered_fields": blockers}
                if not any(key == "email" for _, key in plan):
                    return {"status": "needs_attention", "reason": "A supported application form was not found"}
                for form in page.locator("form").all():
                    action = urljoin(page.url, form.get_attribute("action") or page.url)
                    if not sandbox and urlsplit(action).hostname not in POST_HOSTS:
                        return {"status": "needs_attention", "reason": "Form posts outside supported ATS"}
                for field, key in plan:
                    if key == "resume":
                        field.set_input_files({"name": "resume.pdf", "mimeType": "application/pdf",
                                               "buffer": pdf_bytes})
                    else:
                        field.fill(values[key])
                        if field.input_value() != values[key]:
                            return {"status": "needs_attention", "reason": "Filled field did not verify"}
                submit = page.get_by_role("button", name=re.compile(r"^(submit( application)?|send application)$", re.I))
                if submit.count() != 1:
                    return {"status": "needs_attention", "reason": "Final submission control is ambiguous"}
                submit.click()
                # Never infer success from a click or navigation alone.
                success = page.get_by_text(re.compile(
                    r"application (has been |was )?(received|submitted)|thank you for applying", re.I))
                try:
                    success.first.wait_for(state="visible", timeout=12000)
                except Exception:
                    return {"status": "needs_attention", "uncertain": True,
                            "reason": "No explicit receipt; reconcile employer portal before retrying"}
                return {"status": "submitted", "demo": sandbox, "at": now(),
                        "confirmation": success.first.inner_text()[:500],
                        "fields_filled": len(plan), "url": page.url}
            finally:
                browser.close()
