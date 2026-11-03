from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from .intelligence import extract_skills
from .models import DiscoveryRequest, Job


def plain(text):
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def discover(request: DiscoveryRequest):
    """Read published ATS boards without employer credentials.

    URLs are constructed from an identifier, never fetched from arbitrary input.
    Submission uses the hosted form; employer-only POST APIs aren't misrepresented
    as applicant APIs.
    """
    if request.source == "jobspy":
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise ValueError("Install optional discovery: pip install '.[jobspy]'") from exc
        frame = scrape_jobs(site_name=["indeed"], search_term=request.query,
                            location=request.location, country_indeed="south africa",
                            results_wanted=request.limit, hours_old=72, verbose=0)
        jobs = []
        for row in frame.fillna("").to_dict("records"):
            text = plain(str(row.get("description") or row.get("title", "")))
            if len(text) < 20:
                text += " — open original posting to verify full requirements."
            jobs.append(Job(title=str(row["title"]), company=str(row["company"]),
                            location=str(row.get("location") or request.location), description=text,
                            url=str(row.get("job_url_direct") or row["job_url"]), source="jobspy",
                            required_skills=extract_skills(text)))
        return jobs
    if not request.board:
        raise ValueError("A company board identifier is required")
    if request.source == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{request.board}/jobs?content=true"
    else:
        url = f"https://api.lever.co/v0/postings/{request.board}?mode=json&limit=100"
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get(url, headers={"User-Agent": "ApplyAtlas/0.1 job discovery"})
        response.raise_for_status()
        data = response.json()
    jobs = []
    for item in data.get("jobs", []) if isinstance(data, dict) else data:
        if request.source == "greenhouse":
            text = plain(item.get("content", ""))
            title, location, job_url = item["title"], item["location"]["name"], item["absolute_url"]
        else:
            text = plain(item.get("descriptionPlain") or item.get("description"))
            for section in item.get("lists", []):
                text += " " + plain(section.get("content", ""))
            title, location, job_url = item["text"], item["categories"].get("location", "Remote"), item["applyUrl"]
        if request.query and request.query.casefold() not in (title + " " + text).casefold():
            continue
        # Only explicit 'N+ years' requirements, never invented experience demands.
        years = re.findall(r"(\d{1,2})\+?\s+years?\s+(?:of\s+)?experience", text, re.I)
        jobs.append(Job(title=title, company=request.board, location=location or "Unspecified",
                        description=text if len(text) >= 20 else title + " — review original requirements.",
                        url=job_url, source=request.source, required_skills=extract_skills(text),
                        min_years=float(min(map(int, years))) if years else 0))
        if len(jobs) >= request.limit:
            break
    return jobs
