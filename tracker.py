#!/usr/bin/env python3
"""
Nuclear Jobs Scraper.

  python tracker.py scrape      — visit every portal, save snapshot, update dashboard
  python tracker.py display     — print new jobs to terminal
  python tracker.py dashboard   — regenerate dashboard.html without scraping
"""

import json
import random
import re
import sys
from datetime import datetime, date as _date
from pathlib import Path

SNAPSHOTS_DIR  = Path("snapshots")
PORTALS_FILE   = Path("job_portals.txt")
DASHBOARD_FILE = Path("dashboard.html")

# Tried in order; first selector that yields >= 1 result wins.
SELECTORS = [
    # Workday
    "[data-automation-id='jobTitle']",
    # Greenhouse.io
    ".opening a",
    # Lever
    "h5.posting-name",
    ".posting-title h5",
    # iCIMS
    ".iCIMS_JobTitle a",
    ".iCIMS_JobTitle",
    # BambooHR
    ".BambooHR-ATS-board-item-title",
    "a.job-listing-title",
    # Breezy HR
    ".position h2",
    "h2.position-title",
    # SmartRecruiters
    ".jobTitle",
    # SAP SuccessFactors
    ".jobResultItem .jobTitle a",
    ".sfdc-jobtitle",
    # Taleo
    ".oracleATSResultsTable td a",
    "table.reqListTable td a",
    # Njoyn
    "td.col-title a",
    "td.jobtitle a",
    # Workable
    "li.job-list-item h2",
    "li.job-list-item a",
    # Generic class-name patterns
    "[class*='job-title']",
    "[class*='job_title']",
    "[class*='jobtitle']",
    "[class*='posting-title']",
    "[class*='position-title']",
    "[class*='role-title']",
    "[class*='vacancy-title']",
    "[class*='career-title']",
    "[class*='opening-title']",
    "[class*='requisition-title']",
    # Scoped list headings
    "li h3",
    "li h4",
]

_SKIP_PREFIXES = (
    "showing ",
    "filter results",
    "search results",
    "no jobs",
    "no positions",
    "no openings",
    "candidate menu",
    "set a job alert",
)

# Exact titles that are column headers / UI labels, not real jobs
_SKIP_EXACT = {"title", "location", "date", "department", "company", "category", "type"}

# Location strings from Workday include an "aria label" prefix like "locations Bruce Power"
_LOC_LABEL_RE = re.compile(r"^(locations?|city|region|area|office|site)\s+", re.I)

MIN_LEN = 4
MAX_LEN = 120

# Single round-trip JS: extracts title, url, and location for every matched element.
_EXTRACT_JS = """
(elements) => {
    const LOC_SELS = [
        '[data-automation-id="primaryLocation"]',
        '[data-automation-id="locations"]',
        '.location',
        '.sort-by-location',
        '.posting-categories .sort-by-location',
        '[class*="location"i]',
        '[class*="city"i]',
        '[class*="region"i]',
        '.job-location',
        '.jobLocation',
        'span[class*="Location"]'
    ];

    function getUrl(el) {
        if (el.tagName === 'A' && el.href) return el.href;
        const inner = el.querySelector('a[href]');
        if (inner) return inner.href;
        for (let p = el.parentElement, i = 0; p && i < 6; p = p.parentElement, i++)
            if (p.tagName === 'A' && p.href) return p.href;
        return null;
    }

    function getLocation(el) {
        for (let c = el.parentElement, level = 0; c && level < 6; c = c.parentElement, level++) {
            for (const sel of LOC_SELS) {
                try {
                    const loc = c.querySelector(sel);
                    if (loc && !el.contains(loc)) {
                        const t = (loc.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (t.length >= 2 && t.length < 80) return t;
                    }
                } catch (e) {}
            }
        }
        return null;
    }

    return elements.map(el => ({
        title: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
        url:   getUrl(el),
        loc:   getLocation(el)
    }));
}
"""


# ── snapshot helpers ──────────────────────────────────────────────────────────

def _snap_date(p: Path) -> str:
    return p.stem[:10]


def _snap_dt(p: Path) -> datetime:
    stem = p.stem
    suffix = stem[11:] if len(stem) > 10 and stem[10] == "_" else ""
    if suffix.isdigit() and len(suffix) == 4:
        return datetime.strptime(stem, "%Y-%m-%d_%H%M")
    return datetime.strptime(stem[:10], "%Y-%m-%d")


def _all_snapshots() -> list[Path]:
    return sorted(SNAPSHOTS_DIR.glob("*.json"), key=_snap_dt)


# ── job normalisation helpers ─────────────────────────────────────────────────

def _job_title(job) -> str:
    """Works with both old string format and new dict format."""
    return job if isinstance(job, str) else job.get("title", "")


def _job_key(job) -> str:
    """Case-folded title used for new/existing comparison."""
    return _job_title(job).lower().strip()


def _to_dict(job) -> dict:
    """Normalise a job entry to {title, url, location}."""
    if isinstance(job, str):
        return {"title": job, "url": None, "location": None}
    return {"title": job.get("title", ""),
            "url":   job.get("url"),
            "location": job.get("location")}


# ── text / job extraction ─────────────────────────────────────────────────────

def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def load_portals():
    entries = []
    for raw in PORTALS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0]
        url  = parts[1] if len(parts) > 1 else parts[0]
        sel  = parts[2] if len(parts) > 2 else None
        entries.append((name, url, sel))
    return entries


def _extract_from_selector(page, selector: str) -> list[dict]:
    """Single JS round-trip: returns [{title, url, location}] for all matches."""
    try:
        raw = page.eval_on_selector_all(selector, _EXTRACT_JS)
    except Exception:
        return []

    results = []
    seen: set[str] = set()
    for item in raw:
        title = _clean(item.get("title", ""))
        if not title or not (MIN_LEN <= len(title) <= MAX_LEN):
            continue
        if any(title.lower().startswith(p) for p in _SKIP_PREFIXES):
            continue
        if title.lower() in _SKIP_EXACT:
            continue

        url = item.get("url")
        if url and (url.startswith("about:") or url.startswith("javascript:")):
            url = None

        loc = item.get("loc")
        if loc:
            loc = _LOC_LABEL_RE.sub("", _clean(loc)).strip()
            if not loc or len(loc) > 60:
                loc = None

        key = _job_key({"title": title})
        if key not in seen:
            seen.add(key)
            results.append({"title": title, "url": url, "location": loc})

    return results


def extract_jobs(page, url: str, custom_selector=None) -> list[dict]:
    try:
        page.goto(url, wait_until="load", timeout=50_000)
    except Exception:
        pass

    selectors_to_try = [custom_selector] if custom_selector else SELECTORS
    combined = ", ".join([custom_selector] if custom_selector else SELECTORS[:25])
    try:
        page.wait_for_selector(combined, timeout=45_000)
    except Exception:
        page.wait_for_timeout(3_000)

    for sel in selectors_to_try:
        results = _extract_from_selector(page, sel)
        if results:
            return results
    return []


# ── diff logic ────────────────────────────────────────────────────────────────

def _daily_new() -> list[tuple[str, dict[str, list[dict]]]]:
    snaps = _all_snapshots()
    if len(snaps) < 2:
        return []

    by_date: dict[str, Path] = {}
    for s in snaps:
        by_date[_snap_date(s)] = s

    dates = sorted(by_date)
    result = []

    for i in range(len(dates) - 1, 0, -1):
        cur  = json.loads(by_date[dates[i]].read_text(encoding="utf-8"))
        prev = json.loads(by_date[dates[i - 1]].read_text(encoding="utf-8"))

        new: dict[str, list[dict]] = {}
        for company, jobs in cur.items():
            prev_keys = {_job_key(j) for j in prev.get(company, [])}
            added = [_to_dict(j) for j in jobs if _job_key(j) not in prev_keys]
            if added:
                new[company] = added

        if new:
            result.append((dates[i], new))

    return result


def _scrape_regressions() -> list[str]:
    """Companies that had jobs in the previous snapshot but returned 0 in the latest one."""
    snaps = _all_snapshots()
    if len(snaps) < 2:
        return []
    latest = json.loads(snaps[-1].read_text(encoding="utf-8"))
    prev   = json.loads(snaps[-2].read_text(encoding="utf-8"))
    return sorted(
        company
        for company, jobs in latest.items()
        if len(jobs) == 0 and len(prev.get(company, [])) > 0
    )


# ── dashboard HTML ────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
      background: #eef2f7;
      color: #1e293b;
      line-height: 1.55;
      min-height: 100vh;
    }

    /* ── Header ── */
    .header {
      background: #0f2044;
      color: #fff;
      padding: 16px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 10;
      box-shadow: 0 2px 10px rgba(0,0,0,.4);
    }
    .header-title { font-size: 1.1rem; font-weight: 700; letter-spacing: .01em; }
    .header-meta  { font-size: .78rem; color: #94a3b8; }

    /* ── Layout ── */
    .main { max-width: 860px; margin: 0 auto; padding: 28px 16px 64px; }

    /* ── Day section ── */
    .day { margin-bottom: 36px; }
    .day-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 2px solid #0f2044;
    }
    .day-name   { font-size: 1rem; font-weight: 700; color: #0f2044; }
    .today-pill {
      font-size: .68rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: .06em; background: #059669; color: #fff;
      padding: 2px 7px; border-radius: 4px;
    }
    .day-badge {
      font-size: .72rem; font-weight: 700;
      background: #2563eb; color: #fff;
      padding: 2px 9px; border-radius: 20px;
      margin-left: auto;
    }

    /* ── Company card ── */
    .company {
      background: #fff;
      border-radius: 8px;
      margin-bottom: 10px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      overflow: hidden;
    }
    .company-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 16px;
      background: #f8fafc;
      border-bottom: 1px solid #f1f5f9;
    }
    .company-name  { font-size: .875rem; font-weight: 600; color: #1e3a8a; }
    .company-count {
      font-size: .7rem; font-weight: 600;
      color: #2563eb; background: #eff6ff;
      padding: 2px 8px; border-radius: 20px;
      white-space: nowrap;
    }

    /* ── Job list ── */
    .job-list { list-style: none; padding: 4px 0; }
    .job-list li {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding: 7px 16px 7px 28px;
      position: relative;
      border-bottom: 1px solid #f8fafc;
    }
    .job-list li:last-child { border-bottom: none; }
    .job-list li::before {
      content: "›";
      position: absolute;
      left: 14px;
      color: #2563eb;
      font-weight: 700;
      font-size: 1.05em;
    }
    .job-title {
      font-size: .86rem;
      color: #374151;
      flex: 1;
      min-width: 0;
    }
    a.job-title {
      color: #1d4ed8;
      text-decoration: none;
    }
    a.job-title:hover {
      text-decoration: underline;
      color: #1e40af;
    }
    .job-loc {
      font-size: .76rem;
      color: #64748b;
      white-space: nowrap;
      flex-shrink: 0;
    }

    /* ── Scrape-failure warning ── */
    .scrape-warning {
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-left: 4px solid #ea580c;
      border-radius: 6px;
      padding: 10px 16px;
      margin-bottom: 24px;
      font-size: .82rem;
      color: #7c2d12;
      line-height: 1.5;
    }
    .scrape-warning strong { color: #9f1239; }

    /* ── Empty state ── */
    .empty { text-align: center; padding: 72px 24px; color: #64748b; }
    .empty h2 {
      font-size: 1.05rem; font-weight: 600;
      color: #334155; margin-bottom: 8px;
    }
    .empty p { font-size: .875rem; }

    /* ── Footer ── */
    .footer { text-align: center; padding: 20px; font-size: .73rem; color: #94a3b8; }

    /* ── Controls bar ── */
    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .filter-select {
      flex: 1;
      min-width: 160px;
      padding: 8px 12px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: .875rem;
      color: #1e293b;
      background: #fff;
      cursor: pointer;
    }
    .run-btn {
      padding: 8px 18px;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 6px;
      font-size: .875rem;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }
    .run-btn:hover:not(:disabled) { background: #1d4ed8; }
    .run-btn:disabled { background: #94a3b8; cursor: not-allowed; }

    /* ── Progress panel ── */
    .progress-panel {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 6px;
      padding: 10px 16px;
      margin-bottom: 16px;
      font-size: .84rem;
      color: #1e40af;
      align-items: center;
      gap: 10px;
    }
    .spinner {
      width: 16px; height: 16px;
      border: 2px solid #bfdbfe;
      border-top-color: #2563eb;
      border-radius: 50%;
      animation: spin .7s linear infinite;
      flex-shrink: 0;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Mobile ── */
    @media (max-width: 600px) {
      .header { flex-wrap: wrap; padding: 12px 14px; gap: 6px; }
      .header-meta { font-size: .72rem; }
      .main { padding: 14px 10px 60px; }
      .day-header { flex-wrap: wrap; gap: 6px; }
      .day-badge { margin-left: 0; }
      .job-list li {
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
        padding: 8px 14px 8px 26px;
      }
      .job-title { word-break: break-word; }
      .job-loc { white-space: normal; }
      .company-head { padding: 9px 12px; }
      .company-name { font-size: .82rem; }
      .controls { gap: 8px; }
      .filter-select { min-width: 0; }
    }
"""


_JS_TEMPLATE = """\
(function () {
  // ── GitHub context (owner/repo from GitHub Pages URL) ──
  function githubCtx() {
    var m = location.hostname.match(/^([^.]+)\\.github\\.io$/);
    if (!m) return null;
    var parts = location.pathname.replace(/^\\//, '').split('/');
    return parts[0] ? { owner: m[1], repo: parts[0] } : null;
  }

  var ctx = githubCtx();
  var runBtn = document.getElementById('run-btn');
  var progressPanel = document.getElementById('progress-panel');
  var progressText  = document.getElementById('progress-text');
  var spinner       = document.getElementById('spinner');
  var PORTAL_COUNT  = __N_PORTALS__;

  // ── Company filter ──
  var filterSelect = document.getElementById('company-filter');

  (function buildFilter() {
    var seen = {}, names = [];
    document.querySelectorAll('.company-name').forEach(function (el) {
      var n = el.textContent;
      if (!seen[n]) { seen[n] = true; names.push(n); }
    });
    names.sort().forEach(function (n) {
      var opt = document.createElement('option');
      opt.value = n; opt.textContent = n;
      filterSelect.appendChild(opt);
    });
  })();

  filterSelect.addEventListener('change', function () {
    var val = filterSelect.value;
    document.querySelectorAll('.company').forEach(function (card) {
      var name = card.querySelector('.company-name').textContent;
      card.style.display = (!val || name === val) ? '' : 'none';
    });
    document.querySelectorAll('.day').forEach(function (day) {
      var anyVisible = [].slice.call(day.querySelectorAll('.company'))
        .some(function (c) { return c.style.display !== 'none'; });
      day.style.display = anyVisible ? '' : 'none';
    });
  });

  // ── Run button ──
  if (!ctx) {
    runBtn.disabled = true;
    runBtn.title = 'Only works when viewed on GitHub Pages';
    runBtn.style.opacity = '0.45';
  }

  runBtn.addEventListener('click', function () {
    triggerScrape().catch(function (e) {
      setStatus('Error: ' + e.message, false);
      runBtn.disabled = !ctx;
    });
  });

  function getPAT() {
    var pat = localStorage.getItem('nj_gh_pat');
    if (!pat) {
      pat = prompt(
        'Enter a GitHub Personal Access Token with the "workflow" scope.\\n' +
        'It will be saved in this browser only (localStorage).'
      );
      if (pat && pat.trim()) localStorage.setItem('nj_gh_pat', pat.trim());
    }
    return pat ? pat.trim() : null;
  }

  function setStatus(msg, showSpinner) {
    progressText.textContent = msg;
    spinner.style.display = showSpinner ? '' : 'none';
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  async function triggerScrape() {
    var pat = getPAT();
    if (!pat) return;

    runBtn.disabled = true;
    progressPanel.style.display = 'flex';
    setStatus('Triggering workflow…', true);

    var startTime = Date.now();
    var apiBase = 'https://api.github.com/repos/' + ctx.owner + '/' + ctx.repo;
    var headers  = {
      'Authorization': 'Bearer ' + pat,
      'Accept': 'application/vnd.github+json',
      'Content-Type': 'application/json'
    };

    var resp = await fetch(apiBase + '/actions/workflows/scrape.yml/dispatches', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ ref: 'main' })
    });

    if (resp.status === 401 || resp.status === 403) {
      localStorage.removeItem('nj_gh_pat');
      setStatus('PAT invalid or expired — try again.', false);
      runBtn.disabled = false;
      return;
    }
    if (!resp.ok) {
      setStatus('Could not trigger workflow (HTTP ' + resp.status + '). Check PAT scope.', false);
      runBtn.disabled = false;
      return;
    }

    // Find the run (takes a few seconds to appear in the API)
    var run = null, attempts = 0;
    setStatus('Workflow queued, waiting for it to start…', true);
    while (!run && attempts < 20) {
      await sleep(4000);
      attempts++;
      try {
        var r = await fetch(
          apiBase + '/actions/runs?event=workflow_dispatch&per_page=5',
          { headers: headers }
        );
        var data = await r.json();
        var runs = data.workflow_runs || [];
        for (var i = 0; i < runs.length; i++) {
          if (new Date(runs[i].created_at).getTime() >= startTime - 20000) {
            run = runs[i]; break;
          }
        }
      } catch (_) {}
    }

    if (!run) {
      setStatus('Could not locate the workflow run. Check the Actions tab on GitHub.', false);
      runBtn.disabled = false;
      return;
    }

    // Poll until completed
    while (true) {
      var elapsed   = Math.round((Date.now() - startTime) / 1000);
      var estimated = Math.min(Math.floor(elapsed / 25), PORTAL_COUNT);

      if (run.status === 'completed') {
        if (run.conclusion === 'success') {
          setStatus('Done! Refreshing…', false);
          await sleep(1500);
          location.reload();
        } else {
          setStatus('Workflow ended: ' + run.conclusion + '. Check the Actions tab for details.', false);
          runBtn.disabled = false;
        }
        return;
      }

      setStatus(estimated + '/' + PORTAL_COUNT + ' employers checked (est.) — ' + elapsed + 's elapsed', true);
      await sleep(15000);

      try {
        var upd = await fetch(run.url, { headers: headers });
        run = await upd.json();
      } catch (_) {}
    }
  }
})();
"""


def generate_dashboard():
    snaps = _all_snapshots()

    if snaps:
        last_dt  = _snap_dt(snaps[-1])
        last_str = f"{last_dt.day} {last_dt.strftime('%B %Y')} at {last_dt.strftime('%H:%M')}"
    else:
        last_str = "never"

    n_portals = len(load_portals())
    n_snaps   = len(snaps)
    today_str = _date.today().isoformat()
    result    = _daily_new()

    if not result:
        content = (
            '    <div class="empty">\n'
            '      <h2>Baseline captured — no comparisons yet</h2>\n'
            '      <p>New jobs will appear here once a second day of snapshots has been collected.</p>\n'
            '    </div>'
        )
    else:
        sections = []
        for date_str, companies in result:
            dt         = datetime.strptime(date_str, "%Y-%m-%d")
            date_label = f"{dt.day} {dt.strftime('%B %Y')}"
            total      = sum(len(j) for j in companies.values())
            today_pill = '<span class="today-pill">today</span>' if date_str == today_str else ""

            cards = []
            for company, jobs in sorted(companies.items()):
                count = f"{len(jobs)} job" + ("s" if len(jobs) != 1 else "")
                items = []
                for job in jobs:
                    j     = _to_dict(job)
                    title = _esc(j["title"])
                    url   = j.get("url")
                    loc   = j.get("location")

                    title_html = (
                        f'<a href="{_esc(url)}" target="_blank" rel="noopener" class="job-title">{title}</a>'
                        if url else
                        f'<span class="job-title">{title}</span>'
                    )
                    loc_html = (
                        f'<span class="job-loc">{_esc(loc)}</span>'
                        if loc else ""
                    )
                    items.append(f"          <li>{title_html}{loc_html}</li>")

                cards.append(
                    f'        <div class="company">\n'
                    f'          <div class="company-head">'
                    f'<span class="company-name">{_esc(company)}</span>'
                    f'<span class="company-count">{count}</span>'
                    f'</div>\n'
                    f'          <ul class="job-list">\n'
                    + "\n".join(items) + "\n"
                    f'          </ul>\n'
                    f'        </div>'
                )

            sections.append(
                f'    <section class="day">\n'
                f'      <div class="day-header">\n'
                f'        <h2 class="day-name">{_esc(date_label)}</h2>\n'
                f'        {today_pill}\n'
                f'        <span class="day-badge">{total} new</span>\n'
                f'      </div>\n'
                f'      <div class="companies">\n'
                + "\n".join(cards) + "\n"
                f'      </div>\n'
                f'    </section>'
            )

        content = "\n".join(sections)

    footer = (
        f'{n_portals} companies tracked'
        f' &nbsp;·&nbsp; {n_snaps} snapshot{"s" if n_snaps != 1 else ""}'
        f'<br>Not checked: Terrestrial Energy, NPX Innovation, Framatome Canada'
        f' — career pages use layouts that can\'t be scraped automatically'
    )

    regressions = _scrape_regressions()
    if regressions:
        reg_names = ", ".join(_esc(c) for c in regressions)
        warning_block = (
            f'    <div class="scrape-warning">\n'
            f'      <strong>Scraping may have failed:</strong> {reg_names} returned 0 jobs '
            f'this run but had results last time. Your IP may be blocked — check these portals manually.\n'
            f'    </div>\n'
        )
    else:
        warning_block = ""

    js = _JS_TEMPLATE.replace("__N_PORTALS__", str(n_portals))

    controls_html = (
        '    <div class="controls">\n'
        '      <select id="company-filter" class="filter-select">'
        '<option value="">All companies</option>'
        '</select>\n'
        '      <button id="run-btn" class="run-btn">&#9654; Run Scraper</button>\n'
        '    </div>\n'
        '    <div id="progress-panel" class="progress-panel" style="display:none">\n'
        '      <div id="spinner" class="spinner"></div>\n'
        '      <span id="progress-text"></span>\n'
        '    </div>\n'
    )

    html = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '  <title>Nuclear Jobs Scraper</title>\n'
        f'  <style>{_CSS}  </style>\n'
        '</head>\n'
        '<body>\n'
        '  <header class="header">\n'
        '    <span class="header-title">Nuclear Jobs Scraper</span>\n'
        f'    <span class="header-meta">Last scraped: {_esc(last_str)}</span>\n'
        '  </header>\n'
        '  <main class="main">\n'
        f'{controls_html}'
        f'{warning_block}'
        f'{content}\n'
        '  </main>\n'
        f'  <footer class="footer">{footer}</footer>\n'
        f'  <script>\n{js}\n  </script>\n'
        '</body>\n'
        '</html>\n'
    )

    DASHBOARD_FILE.write_text(html, encoding="utf-8")


# ── scrape ────────────────────────────────────────────────────────────────────

def scrape():
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    now   = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H%M")
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    snapshot_path = SNAPSHOTS_DIR / f"{stamp}.json"

    if snapshot_path.exists():
        print(f"Snapshot for {stamp} already exists. Delete it to re-scrape.")
        return

    portals  = load_portals()
    snapshot = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            locale="en-CA",
            timezone_id="America/Toronto",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        for name, url, selector in portals:
            print(f"  {name} ... ", end="", flush=True)
            try:
                jobs = extract_jobs(page, url, selector)
                # Deduplicate by title (case-folded)
                seen: set[str] = set()
                unique: list[dict] = []
                for j in jobs:
                    k = _job_key(j)
                    if k not in seen:
                        seen.add(k)
                        unique.append(j)
                unique.sort(key=lambda j: _job_title(j).lower())
                snapshot[name] = unique
                print(f"{len(unique)} job(s)")
            except Exception as exc:
                print(f"ERROR — {exc}")
                snapshot[name] = []

            page.wait_for_timeout(random.randint(1_000, 3_000))

        browser.close()

    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    generate_dashboard()

    existing_dates = sorted({_snap_date(p) for p in _all_snapshots()})
    if len(existing_dates) == 1:
        print(f"\nBaseline saved ({snapshot_path}).")
        print("Open dashboard.html — new jobs will appear from tomorrow.")
    else:
        print(f"\nSnapshot saved. Dashboard updated -> open dashboard.html")


# ── display (terminal) ────────────────────────────────────────────────────────

def display():
    result = _daily_new()
    if not result:
        print("No new jobs yet — need snapshots from at least 2 different days.")
        return
    for date_str, companies in result:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        print(f"\n{dt.day} {dt.strftime('%B %Y')}")
        for company, jobs in sorted(companies.items()):
            print(f"  {company}:")
            for job in jobs:
                j   = _to_dict(job)
                loc = f"  —  {j['location']}" if j.get("location") else ""
                print(f"    {j['title']}{loc}")
                if j.get("url"):
                    print(f"      {j['url']}")
    print()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scrape":
        scrape()
    elif cmd == "display":
        display()
    elif cmd == "dashboard":
        generate_dashboard()
        print(f"Dashboard written to {DASHBOARD_FILE.resolve()}")
    else:
        print("Usage:  python tracker.py  scrape | display | dashboard")
        sys.exit(1)


if __name__ == "__main__":
    main()
