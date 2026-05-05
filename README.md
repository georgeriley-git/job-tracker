# Job Board Tracker

Scrapes career pages daily and shows you only the **new** jobs since your last run.

## Why Python + Playwright?

Modern career pages are almost all JavaScript SPAs — Workday, Taleo, iCIMS, BambooHR, Breezy HR, etc. A plain `requests` call only sees the raw HTML before JS runs, which is usually an empty shell. Playwright launches a real headless Chromium browser, lets the page fully render, then extracts job titles. Snapshots are plain JSON files — no database, no server.

---

## Setup

**1. Install Python dependencies**

```
pip install -r requirements.txt
```

**2. Install the Chromium browser** (one-time, ~130 MB)

```
playwright install chromium
```

---

## Configure your portals

Edit `job_portals.txt`. Each line is:

```
Company Name | URL
```

The script auto-detects the ATS platform (Workday, iCIMS, BambooHR, Greenhouse, Lever, Taleo, Breezy HR, SmartRecruiters, etc.) and picks the right CSS selector automatically.

If auto-detection returns zero jobs for a site, add your own selector as a third field:

```
Example Corp | https://example.com/careers | h2.job-title
```

To find the right selector: open the page in Chrome, right-click a job title → Inspect → right-click the element in DevTools → Copy → Copy selector.

Lines starting with `#` are ignored.

---

## Usage

**First run — saves a baseline (no output):**

```
python tracker.py scrape
```

**Every subsequent run:**

```
python tracker.py scrape     # capture today's snapshot
python tracker.py display    # show new jobs since last run
```

You can run `scrape` and then immediately `display`, but you won't see anything new until the next day's scrape.

---

## Example output

```
30 April
  AtkinsRealis:
    Project Coordinator
    Mechanical Engineer

29 April
  Kinectrics:
    DSA Analyst
```

`display` always shows the full history of additions across all snapshots, newest first.

---

## Snapshots

Saved in `snapshots/YYYY-MM-DD.json`. Running `scrape` twice on the same day is a no-op. To re-scrape today, delete `snapshots/YYYY-MM-DD.json` and run again.

Example snapshot:

```json
{
  "Kinectrics": [
    "DSA Analyst",
    "Electrical Engineer"
  ],
  "Bruce Power": [
    "Reactor Engineer"
  ]
}
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| A site shows `0 job(s)` | Add a custom CSS selector as the third field in `job_portals.txt` |
| `playwright install` hangs | Run it in a terminal with internet access; it downloads ~130 MB |
| A site shows nav items or page titles, not jobs | The fallback selector matched too broadly — add a specific selector |
| `ERROR — Timeout` for a site | The site may block headless browsers; try visiting it manually and report the URL |
