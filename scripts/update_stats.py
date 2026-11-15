#!/usr/bin/env python3
"""Generate assets/generated/stats.svg (GitHub) and leetcode.svg (LeetCode).

Runs inside GitHub Actions (see .github/workflows/profile.yml) using only the
Python standard library. If a data source is unreachable the existing SVG is
left untouched, so the README never shows a broken image.

Env vars: GITHUB_TOKEN, GH_USER (default gopalnayak980), LEETCODE_USER.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from html import escape

GH_USER = os.environ.get("GH_USER", "gopalnayak980")
LC_USER = os.environ.get("LEETCODE_USER", "Gopal_Nayak")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "generated")

SANS = "'Segoe UI','Helvetica Neue',Arial,sans-serif"
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

LANG_COLORS = {
    "JavaScript": "#f7df1e", "Python": "#3776ab", "HTML": "#e34c26", "CSS": "#9b6bff",
    "Java": "#e76f00", "C++": "#00599c", "C": "#7a8ba8", "TypeScript": "#3178c6",
    "EJS": "#a91e50", "Shell": "#89e051", "SCSS": "#c6538c", "Jupyter Notebook": "#da5b0b",
}
FALLBACK_COLORS = ["#00f5ff", "#7b2ff7", "#ff00c8", "#3b82f6", "#22d3a5", "#ffb703"]


# ---------------------------------------------------------------- HTTP helpers
def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gh_headers():
    h = {"User-Agent": "profile-stats", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = "Bearer " + TOKEN
    return h


def gh_rest(path):
    return http_json("https://api.github.com" + path, headers=gh_headers())


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    h = gh_headers()
    h["Content-Type"] = "application/json"
    return http_json("https://api.github.com/graphql", data=body, headers=h)


# ---------------------------------------------------------------- data fetch
def streaks(days):
    """days: list of (date, count) sorted ascending. Returns (current, longest)."""
    longest = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    current = 0
    counts = {d: c for d, c in days}
    d = date.today()
    if counts.get(d, 0) == 0:  # today may not be committed yet
        d -= timedelta(days=1)
    while counts.get(d, 0) > 0:
        current += 1
        d -= timedelta(days=1)
    return current, longest


def fetch_github():
    user = gh_rest(f"/users/{GH_USER}")
    repos = gh_rest(f"/users/{GH_USER}/repos?per_page=100&type=owner")
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    langs = {}
    for r in repos:
        if r.get("fork"):
            continue
        try:
            for k, v in gh_rest(f"/repos/{GH_USER}/{r['name']}/languages").items():
                langs[k] = langs.get(k, 0) + v
        except Exception as exc:  # one repo failing should not kill the card
            print("languages failed for", r["name"], exc, file=sys.stderr)
    data = {
        "repos": user.get("public_repos", len(repos)),
        "followers": user.get("followers", 0),
        "stars": stars,
        "langs": sorted(langs.items(), key=lambda kv: -kv[1])[:6],
        "contrib": None, "current": None, "longest": None,
    }
    if TOKEN:
        q = """query($login:String!){user(login:$login){contributionsCollection{
          contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
        try:
            cal = gh_graphql(q, {"login": GH_USER})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            days = sorted(
                (date.fromisoformat(d["date"]), d["contributionCount"])
                for w in cal["weeks"] for d in w["contributionDays"]
            )
            data["contrib"] = cal["totalContributions"]
            data["current"], data["longest"] = streaks(days)
        except Exception as exc:
            print("contribution calendar failed:", exc, file=sys.stderr)
    return data


def fetch_leetcode():
    query = """query($u:String!){matchedUser(username:$u){submitStatsGlobal{acSubmissionNum{difficulty count}}}}"""
    body = json.dumps({"query": query, "variables": {"u": LC_USER}}).encode()
    headers = {
        "Content-Type": "application/json",
        "Referer": f"https://leetcode.com/u/{LC_USER}/",
        "User-Agent": "Mozilla/5.0 (profile-stats)",
    }
    res = http_json("https://leetcode.com/graphql", data=body, headers=headers)
    rows = res["data"]["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]
    out = {r["difficulty"]: r["count"] for r in rows}
    return {"total": out.get("All", 0), "easy": out.get("Easy", 0),
            "medium": out.get("Medium", 0), "hard": out.get("Hard", 0)}


# ---------------------------------------------------------------- rendering
def _fmt(v):
    return "--" if v is None else f"{v:,}"


def _frame(w, h, title, body, defs=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<defs>
<linearGradient id="line" x1="0" x2="1"><stop offset="0" stop-color="#00f5ff"/><stop offset=".5" stop-color="#7b2ff7"/><stop offset="1" stop-color="#ff00c8"/></linearGradient>
<linearGradient id="panel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0e1330"/><stop offset="1" stop-color="#070918"/></linearGradient>
{defs}
</defs>
<rect width="{w}" height="{h}" rx="16" fill="url(#panel)"/>
<rect x=".75" y=".75" width="{w-1.5}" height="{h-1.5}" rx="15.5" fill="none" stroke="url(#line)" stroke-opacity=".7" stroke-width="1.5"/>
{body}
</svg>
"""


def render_stats(d=None):
    W, H = 860, 330
    tiles = [
        ("PUBLIC REPOS", d and d["repos"]), ("TOTAL STARS", d and d["stars"]),
        ("FOLLOWERS", d and d["followers"]), ("CONTRIBUTIONS", d and d["contrib"]),
        ("CURRENT STREAK", d and d["current"]), ("LONGEST STREAK", d and d["longest"]),
    ]
    parts = [f'<text x="28" y="40" font-family="{MONO}" font-size="14" letter-spacing="2" fill="#00f5ff">// GITHUB TELEMETRY · LAST 12 MONTHS</text>']
    parts.append(f'<text x="{W-28}" y="40" text-anchor="end" font-family="{MONO}" font-size="13" fill="#8b9bc0">{"live via GitHub Actions" if d else "syncing: run the workflow once"}</text>')
    tw, th, gap = 125, 82, 11
    x0 = 28
    for i, (label, val) in enumerate(tiles):
        x = x0 + i * (tw + gap)
        parts.append(f'<rect x="{x}" y="62" width="{tw}" height="{th}" rx="10" fill="#0a0d24" stroke="#26306b" stroke-width="1"/>')
        parts.append(f'<text x="{x+tw/2}" y="104" text-anchor="middle" font-family="{SANS}" font-size="30" font-weight="800" fill="#ffffff">{_fmt(val)}</text>')
        parts.append(f'<text x="{x+tw/2}" y="128" text-anchor="middle" font-family="{MONO}" font-size="10.5" letter-spacing="1" fill="#8b9bc0">{label}</text>')
    parts.append(f'<text x="28" y="182" font-family="{MONO}" font-size="14" letter-spacing="2" fill="#00f5ff">// LANGUAGE DISTRIBUTION</text>')
    langs = (d and d["langs"]) or []
    total = sum(v for _, v in langs) or 1
    if langs:
        bx, bw = 28, W - 56
        cx = bx
        parts.append(f'<clipPath id="barclip"><rect x="{bx}" y="196" width="{bw}" height="14" rx="7"/></clipPath><g clip-path="url(#barclip)">')
        for i, (name, v) in enumerate(langs):
            seg = bw * v / total
            col = LANG_COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
            parts.append(f'<rect x="{cx:.1f}" y="196" width="{seg:.1f}" height="14" fill="{col}"/>')
            cx += seg
        parts.append("</g>")
        for i, (name, v) in enumerate(langs):
            col = LANG_COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
            lx = 28 + (i % 3) * 270
            ly = 244 + (i // 3) * 36
            parts.append(f'<circle cx="{lx+7}" cy="{ly-5}" r="7" fill="{col}"/>')
            parts.append(f'<text x="{lx+24}" y="{ly}" font-family="{SANS}" font-size="16" font-weight="600" fill="#e6f1ff">{escape(name)}</text>')
            parts.append(f'<text x="{lx+236}" y="{ly}" text-anchor="end" font-family="{MONO}" font-size="14" fill="#8b9bc0">{100*v/total:.1f}%</text>')
    else:
        parts.append(f'<rect x="28" y="196" width="{W-56}" height="14" rx="7" fill="#151a3d"/>')
        parts.append(f'<text x="28" y="250" font-family="{SANS}" font-size="16" fill="#8b9bc0">Language data appears after the first workflow run (Actions tab, Run workflow).</text>')
    return _frame(W, H, "GitHub statistics dashboard", "\n".join(parts))


def render_leetcode(d=None):
    W, H = 860, 210
    parts = [f'<text x="28" y="40" font-family="{MONO}" font-size="14" letter-spacing="2" fill="#ffa116">// LEETCODE · {escape(LC_USER)}</text>']
    parts.append(f'<text x="{W-28}" y="40" text-anchor="end" font-family="{MONO}" font-size="13" fill="#8b9bc0">{"live via GitHub Actions" if d else "syncing: run the workflow once"}</text>')
    total = d["total"] if d else None
    parts.append(f'<text x="28" y="122" font-family="{SANS}" font-size="64" font-weight="800" fill="#ffffff">{_fmt(total)}</text>')
    parts.append(f'<text x="30" y="152" font-family="{MONO}" font-size="13" letter-spacing="1.5" fill="#8b9bc0">PROBLEMS SOLVED</text>')
    rows = [("Easy", "#22d3a5", d and d["easy"]), ("Medium", "#ffb703", d and d["medium"]), ("Hard", "#ff4d6d", d and d["hard"])]
    top = max([r[2] or 0 for r in rows] + [1])
    for i, (name, col, val) in enumerate(rows):
        y = 78 + i * 38
        parts.append(f'<text x="300" y="{y+5}" font-family="{SANS}" font-size="16" font-weight="600" fill="#e6f1ff">{name}</text>')
        parts.append(f'<rect x="390" y="{y-8}" width="360" height="12" rx="6" fill="#151a3d"/>')
        w = 360 * (val or 0) / top
        if w:
            parts.append(f'<rect x="390" y="{y-8}" width="{w:.1f}" height="12" rx="6" fill="{col}"/>')
        parts.append(f'<text x="770" y="{y+4}" font-family="{MONO}" font-size="15" fill="#ffffff">{_fmt(val)}</text>')
    return _frame(W, H, "LeetCode statistics", "\n".join(parts))


def write(name, content):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("wrote", path)


def main():
    try:
        write("stats.svg", render_stats(fetch_github()))
    except Exception as exc:
        print("GitHub stats failed, keeping previous file:", exc, file=sys.stderr)
    try:
        write("leetcode.svg", render_leetcode(fetch_leetcode()))
    except Exception as exc:
        print("LeetCode stats failed, keeping previous file:", exc, file=sys.stderr)


if __name__ == "__main__":
    main()
