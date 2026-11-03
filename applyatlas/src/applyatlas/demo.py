from .models import Candidate, Evidence, Job, Policy


def seed(store):
    candidate = Candidate(
        id="demo-client", name="Alex Morgan", email="alex@example.com", phone="+27 00 000 0000",
        location="Johannesburg, South Africa", years_experience=3,
        desired_titles=["Data Engineer", "Python Developer", "Analytics Engineer"],
        preferred_locations=["South Africa", "Remote", "Johannesburg"],
        evidence=[
            Evidence(id="etl-01", text="Built Python and SQL data pipelines with validation checks and scheduled refreshes.",
                     skills=["Python", "SQL", "ETL"]),
            Evidence(id="api-02", text="Developed a FastAPI service, packaged it with Docker, and maintained the project in Git.",
                     skills=["FastAPI", "Docker", "Git"]),
            Evidence(id="bi-03", text="Created Power BI dashboards and used Excel and statistics to investigate quality trends.",
                     skills=["Power BI", "Excel", "Statistics"]),
            Evidence(id="agent-04", text="Built a LangGraph workflow and tested browser form automation with Playwright.",
                     skills=["LangGraph", "Playwright", "Python"]),
        ], policy=Policy(min_score=65))
    # Explicit demo action resets only this fictional profile, not any real client.
    store.save_candidate(candidate)
    roles = [
        ("Data Engineer", "Northstar Labs", "Johannesburg, South Africa", ["Python", "SQL", "ETL", "Docker"], 2),
        ("Python Developer", "Cedar Systems", "Remote", ["Python", "FastAPI", "Docker", "Git"], 2),
        ("Analytics Engineer", "Orbit Analytics", "Cape Town, South Africa", ["SQL", "Power BI", "Statistics"], 2),
        ("AI Automation Engineer", "Fieldwork AI", "Remote", ["Python", "LangGraph", "Playwright"], 2),
        ("Senior Platform Engineer", "Harbour Cloud", "London, United Kingdom", ["Kubernetes", "AWS", "Java"], 8),
        ("Machine Learning Engineer", "Aster Research", "Remote", ["Python", "PyTorch", "Machine Learning"], 4),
    ]
    for index, (title, company, location, skills, years) in enumerate(roles):
        store.save_job(Job(title=title, company=company, location=location,
                           description=f"Join {company} as a {title}. Work with {', '.join(skills)}. "
                           f"The role requests {years} years of experience. All demo roles are fictional.",
                           url=f"https://demo.applyatlas.invalid/jobs/{index}", source="demo",
                           required_skills=skills, min_years=years))
    return candidate.id
