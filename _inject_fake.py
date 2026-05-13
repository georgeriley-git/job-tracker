"""
Injects fake historical snapshots so the dashboard has multiple days to display.
Run:   python _inject_fake.py
Undo:  python _inject_fake.py --undo
"""
import json
import sys
from pathlib import Path

SNAPSHOTS_DIR = Path("snapshots")

# Fake new jobs per date: (date, company, [(title, url, location), ...])
FAKE_ADDITIONS = [
    # 29 April
    ("2026-04-29", "AtkinsRealis", [
        ("Project Manager, Decommissioning", "https://slihrms.wd3.myworkdayjobs.com/en-US/Careers", "Toronto, ON"),
        ("Systems Safety Analyst",           "https://slihrms.wd3.myworkdayjobs.com/en-US/Careers", "Mississauga, ON"),
    ]),
    ("2026-04-29", "OPG", [
        ("Outage Coordinator, Nuclear", "https://jobs.opg.com/search/", "Pickering, ON"),
    ]),
    ("2026-04-29", "Kinectrics", [
        ("Electrical Engineer, Nuclear Instrumentation", "https://careers.kinectrics.com/go/View-all-Jobs/2625717/", "Toronto, ON"),
    ]),

    # 30 April
    ("2026-04-30", "Kinectrics", [
        ("Reactor Physics Analyst",      "https://careers.kinectrics.com/go/View-all-Jobs/2625717/", "Toronto, ON"),
        ("Cybersecurity Engineer, OT",   "https://careers.kinectrics.com/go/View-all-Jobs/2625717/", "Toronto, ON"),
    ]),
    ("2026-04-30", "BWXT", [
        ("Nuclear Materials Process Engineer", "https://careers.bwxt.com/search/", "Cambridge, ON"),
    ]),
    ("2026-04-30", "Bruce Power", [
        ("Nuclear Chemistry Technician", "https://brucepower.wd3.myworkdayjobs.com/BrucePower/", "Tiverton, ON"),
    ]),

    # 1 May
    ("2026-05-01", "Bruce Power", [
        ("Licensed Reactor Operator",  "https://brucepower.wd3.myworkdayjobs.com/BrucePower/", "Tiverton, ON"),
        ("Shift Supervisor, Nuclear",  "https://brucepower.wd3.myworkdayjobs.com/BrucePower/", "Tiverton, ON"),
    ]),
    ("2026-05-01", "Hatch", [
        ("Senior Project Engineer, Nuclear", "https://jobs.hatch.com/search/?q=&locationsearch=mississauga", "Mississauga, ON"),
    ]),
    ("2026-05-01", "NWMO", [
        ("Project Manager, Construction",  "https://careers.nwmo.ca/vacancies.html", "Toronto, ON"),
        ("Geoscientist, Deep Geology",     "https://careers.nwmo.ca/vacancies.html", "Toronto, ON"),
    ]),

    # 2 May
    ("2026-05-02", "AtkinsRealis", [
        ("Senior I&C Design Engineer", "https://slihrms.wd3.myworkdayjobs.com/en-US/Careers", "Toronto, ON"),
        ("Lead Reactor Engineer",      "https://slihrms.wd3.myworkdayjobs.com/en-US/Careers", "Mississauga, ON"),
    ]),
    ("2026-05-02", "OPG", [
        ("Radiological Protection Technician", "https://jobs.opg.com/search/", "Pickering, ON"),
    ]),
    ("2026-05-02", "Westinghouse", [
        ("Fuel Engineering Analyst", "https://careers.westinghousenuclear.com/search/", "Mississauga, ON"),
    ]),
    ("2026-05-02", "CNL", [
        ("Radiochemistry Research Scientist", "https://tre.tbe.taleo.net/tre01/ats/careers/v2/searchResults?org=CNLLTD&cws=37", "Chalk River, ON"),
    ]),
]

FAKE_DATES = sorted({d for d, _, _ in FAKE_ADDITIONS})

if "--undo" in sys.argv:
    removed = []
    for d in FAKE_DATES:
        for p in SNAPSHOTS_DIR.glob(f"{d}_0000_fake.json"):
            p.unlink()
            removed.append(p.name)
    if removed:
        print("Removed:", ", ".join(removed))
    else:
        print("Nothing to remove.")
    sys.exit(0)

# ── Load the real baseline (prefer dict-format 1032 snapshot, fall back to 0000) ─
candidates = sorted(SNAPSHOTS_DIR.glob("2026-05-02_*.json"))
# Filter to real (non-fake) snapshots and pick the latest
real_snaps = [p for p in candidates if "_fake" not in p.stem]
baseline_path = real_snaps[-1] if real_snaps else candidates[-1]
raw_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

# Normalise baseline to dict format: {company: [{"title":…, "url":…, "location":…}]}
def _normalise(jobs):
    out = []
    for j in jobs:
        if isinstance(j, str):
            out.append({"title": j, "url": None, "location": None})
        else:
            out.append({"title": j.get("title", ""), "url": j.get("url"), "location": j.get("location")})
    return out

running: dict[str, list[dict]] = {c: _normalise(js) for c, js in raw_baseline.items()}

# ── Build cumulative snapshots per fake date ──────────────────────────────────
for date in FAKE_DATES:
    day_additions = [(c, jobs) for d, c, jobs in FAKE_ADDITIONS if d == date]
    for company, new_jobs in day_additions:
        existing_titles = {j["title"].lower() for j in running.get(company, [])}
        running.setdefault(company, [])
        for title, url, loc in new_jobs:
            if title.lower() not in existing_titles:
                running[company].append({"title": title, "url": url, "location": loc})
                existing_titles.add(title.lower())
        running[company].sort(key=lambda j: j["title"].lower())

    out = SNAPSHOTS_DIR / f"{date}_0000_fake.json"
    out.write_text(json.dumps(running, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for v in running.values())
    print(f"  {out.name}  ({total} total jobs)")

print("\nFake snapshots written. Regenerating dashboard...")
