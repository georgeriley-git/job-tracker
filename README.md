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

---

## GitHub Deployment (run automatically + view on phone)

The scraper runs on GitHub's servers at **12:00 UTC and 19:00 UTC** every day via GitHub Actions, and the dashboard is served as a static website via GitHub Pages.

---

### Step 1 — Push to GitHub for the first time

Create a new **empty** repository on github.com (no README, no .gitignore), then run these commands in your local `job-tracker` folder:

```
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
git branch -M main
git push -u origin main
```

Replace `YOUR-USERNAME` and `YOUR-REPO-NAME` with your actual GitHub username and the name you gave the repo.

---

### Step 2 — Enable GitHub Actions

GitHub Actions is enabled automatically for new repos. To confirm it's on:

1. Open your repo on github.com
2. Click the **Actions** tab
3. If you see a prompt asking you to enable Actions, click **Enable**

The workflow (`.github/workflows/scrape.yml`) will now run on schedule and whenever you click **Run workflow** from the Actions tab.

---

### Step 3 — Enable GitHub Pages

1. Open your repo on github.com → **Settings** → **Pages** (left sidebar)
2. Under **Source**, choose **Deploy from a branch**
3. Set the branch to **main** and the folder to **/ (root)**
4. Click **Save**

After a minute, GitHub will show you the URL where your site is live — something like:

```
https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/dashboard.html
```

Bookmark this URL on your phone. The dashboard updates automatically after each scrape.

---

### Step 4 — Enable the "Run Scraper" button

The dashboard has a **▶ Run Scraper** button that triggers a scrape immediately from any browser. It calls the GitHub API and needs a Personal Access Token (PAT) to do so.

**Create a PAT:**

1. Go to github.com → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Give it a name like `job-tracker-run`
4. Under **Select scopes**, check **workflow**
5. Click **Generate token** and copy the token (you can only see it once)

**Use the PAT:**

The token is stored in your browser's local storage — it never leaves your device and is never sent anywhere except the GitHub API.

1. Open your dashboard at the GitHub Pages URL
2. Click **▶ Run Scraper**
3. Paste your PAT when prompted — it is saved automatically for future clicks
4. The button shows live progress ("4/18 employers checked (est.)") and refreshes the page when the scrape is done

To clear a saved PAT (e.g., if it expires), open your browser's developer console and run:

```js
localStorage.removeItem('nj_gh_pat')
```

---

### Schedule

The scraper runs automatically at:

| Time | Ontario (EDT, UTC−4) | Ontario (EST, UTC−5) |
|---|---|---|
| 12:00 UTC | 8:00 AM | 7:00 AM |
| 19:00 UTC | 3:00 PM | 2:00 PM |

Each run commits a new snapshot JSON file and an updated `dashboard.html` to the repo.
