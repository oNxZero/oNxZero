#!/usr/bin/env python3
"""Render the profile using public GitHub data and the Python standard library."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USER = "oNxZero"
ROOT = Path(__file__).resolve().parents[1]
C = {
    "base": "#24273a", "mantle": "#1e2030", "crust": "#181926",
    "surface0": "#363a4f", "surface1": "#494d64", "surface2": "#5b6078",
    "overlay": "#8087a2", "muted": "#a5adcb", "subtext": "#b8c0e0",
    "text": "#cad3f5", "lavender": "#b7bdf8", "mauve": "#c6a0f6",
    "blue": "#8aadf4", "teal": "#8bd5ca", "green": "#a6da95",
    "peach": "#f5a97f", "yellow": "#eed49f", "pink": "#f5bde6",
}
PROJECTS = [
    {"repo": "Automater", "file": "automater", "title": "Automater",
     "category": "LINUX TOOL", "color": "lavender", "icon": "cursor",
     "lines": ["Record input. Edit the workflow.", "Play it back on Linux."],
     "stack": "Python  /  X11 + Wayland"},
    {"repo": "CTM-Gen", "file": "ctm-gen", "title": "CTM Generator",
     "category": "TEXTURE TOOL", "color": "teal", "icon": "tiles",
     "lines": ["One block texture in.", "A connected texture pack out."],
     "stack": "Python  /  Flet + Pillow"},
    {"repo": "spuds-shop-reforged", "file": "spuds-shop-reforged",
     "title": "Spuds Shop Reforged", "category": "MINECRAFT / COMMUNITY FORK",
     "color": "peach", "icon": "shop",
     "lines": ["Player shops, trade accounting,", "and fewer ways to dupe items."],
     "stack": "Java  /  NeoForge"},
    {"repo": "NotEnoughRevivesReforged", "file": "not-enough-revives",
     "title": "Not Enough Revives", "category": "MINECRAFT / REFORGED",
     "color": "green", "icon": "revive",
     "lines": ["Downed players. Cooperative revives.", "Server-side fixes and customization."],
     "stack": "Java  /  NeoForge"},
]


def request(url, *, api=False):
    headers = {"User-Agent": f"{USER}-profile", "Accept-Language": "en-US,en;q=0.9"}
    if api:
        if not url.startswith("https://api.github.com/"):
            raise ValueError("API credentials may only be sent to api.github.com")
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        if os.environ.get("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code < 500 and error.code != 429:
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def api(path):
    return json.loads(request(f"https://api.github.com{path}", api=True))


class CalendarParser(HTMLParser):
    """Read dates and contribution counts from GitHub's anonymous calendar."""

    def __init__(self):
        super().__init__()
        self.cells = {}
        self.tips = {}
        self.tip_id = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"td", "rect"} and "data-date" in attrs:
            self.cells[attrs["id"]] = {
                "date": attrs["data-date"], "level": int(attrs["data-level"]),
            }
        if tag == "tool-tip" and "for" in attrs:
            self.tip_id = attrs["for"]
            self.tips[self.tip_id] = ""

    def handle_data(self, data):
        if self.tip_id is not None:
            self.tips[self.tip_id] += data

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.tip_id = None

    def days(self, today, *, minimum=350):
        result = []
        for cell_id, cell in self.cells.items():
            if date.fromisoformat(cell["date"]) > today:
                continue
            match = re.search(r"\b(No|[\d,]+) contributions? on\b", self.tips.get(cell_id, ""))
            if not match or cell["level"] not in range(5):
                raise ValueError(f"Unrecognized contribution data for {cell['date']}")
            count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
            if (count == 0) != (cell["level"] == 0):
                raise ValueError(f"Inconsistent contribution level for {cell['date']}")
            result.append({**cell, "count": count})
        result.sort(key=lambda day: day["date"])
        if len(result) < minimum or len({d["date"] for d in result}) != len(result):
            raise ValueError("Contribution calendar is missing or incomplete; keeping existing assets")
        if result:
            span = (date.fromisoformat(result[-1]["date"]) - date.fromisoformat(result[0]["date"])).days + 1
            if span != len(result) or result[-1]["date"] != today.isoformat():
                raise ValueError("Contribution calendar dates are incomplete or stale")
        return result


def language_repos(repos):
    return [r for r in repos if not r["private"] and not r["fork"]
            and not r["archived"] and r["name"].lower() != USER.lower()]


def collect(today):
    repos = []
    page = 1
    while True:
        batch = api(f"/users/{USER}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Unexpected repository response")
        repos.extend(r for r in batch if r.get("private") is False)
        if len(batch) < 100:
            break
        page += 1
    if not repos:
        raise ValueError("No public repositories found")
    calendar = CalendarParser()
    # GitHub's `to` parameter selects a calendar year, not a rolling date range.
    calendar.feed(request(f"https://github.com/users/{USER}/contributions"))
    days = calendar.days(today)
    languages = Counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for detected in pool.map(lambda r: api(f"/repos/{USER}/{quote(r['name'], safe='')}/languages"),
                                 language_repos(repos)):
            languages.update(detected)
    return {
        "updated": today.isoformat(), "days": days,
        "repos": [{k: r[k] for k in ("name", "description", "html_url", "private", "fork",
                                    "archived", "stargazers_count", "language")} for r in repos],
        "languages": dict(languages.most_common()),
    }


def rect(x, y, w, h, fill, radius=0, **attrs):
    extra = " ".join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{C.get(fill, fill)}" {extra}/>'


def text(x, y, value, size=14, color="text", *, mono=False, weight=400, anchor="start", spacing=0):
    family = "ui-monospace, SFMono-Regular, Consolas, monospace" if mono else "-apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif"
    return (f'<text x="{x}" y="{y}" fill="{C.get(color, color)}" font-size="{size}" '
            f'font-family="{family}" font-weight="{weight}" text-anchor="{anchor}" '
            f'letter-spacing="{spacing}">{escape(str(value))}</text>')


def line(x1, y1, x2, y2, color="surface0", **attrs):
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C[color]}" {extra}/>'


def svg(width, height, title, body, description=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
            f'<title id="title">{escape(title)}</title>\n<desc id="desc">{escape(description or title)}</desc>\n'
            + "\n".join(body) + "\n</svg>\n")


def frame(width, height):
    return rect(0.5, 0.5, width-1, height-1, "base", 12, stroke=C["surface0"])


def header(*, compact=False):
    if compact:
        body = [frame(440, 230), text(28, 34, "~/oNxZero", 12, "muted", mono=True),
                text(26, 112, "oNxZero", 66, weight=700, spacing=-3),
                text(28, 151, "making what i need.", 17, "subtext"),
                text(28, 175, "sometimes releasing it.", 17, "subtext"),
                text(28, 210, "LINUX TOOLS / MINECRAFT MODS / UTILITIES", 10, "teal", mono=True)]
        for i, color in enumerate(["lavender", "mauve", "pink", "peach", "yellow", "green", "teal", "blue"]):
            body.append(rect(296+i*14, 24, 8, 8, color, 2))
        return svg(440, 230, "oNxZero", body)
    body = [frame(880, 230), text(32, 34, "~/oNxZero", 12, "muted", mono=True)]
    for i, color in enumerate(["lavender", "mauve", "pink", "peach", "yellow", "green", "teal", "blue"]):
        body.append(rect(716 + i * 15, 24, 9, 9, color, 2))
    body += [text(30, 112, "oNxZero", 76, weight=700, spacing=-3),
             text(33, 151, "making what i need. sometimes releasing it.", 17, "subtext"),
             text(33, 198, "LINUX TOOLS", 11, "lavender", mono=True, spacing=1),
             text(151, 198, "/", 11, "surface2", mono=True),
             text(176, 198, "MINECRAFT MODS", 11, "teal", mono=True, spacing=1),
             text(317, 198, "/", 11, "surface2", mono=True),
             text(341, 198, "SMALL UTILITIES", 11, "peach", mono=True, spacing=1)]
    # A small pixel N / slashed zero, drawn directly rather than using an image service.
    n = ["1100011", "1110011", "1111011", "1101111", "1100111", "1100011", "1100011"]
    zero = ["0111110", "1100011", "1100111", "1101011", "1110011", "1100011", "0111110"]
    for row in range(9):
        for col in range(18):
            body.append(rect(623 + col*11, 66 + row*11, 2, 2, "surface1", 0.5))
    for glyph, origin, color in [(n, 630, "lavender"), (zero, 728, "teal")]:
        for y, row in enumerate(glyph):
            for x, bit in enumerate(row):
                if bit == "1":
                    body.append(rect(origin+x*11, 75+y*11, 8, 8, color, 1))
    return svg(880, 230, "oNxZero", body, "making what i need. sometimes releasing it. Linux tools, Minecraft mods, small utilities.")


def icon(kind, x, y, color):
    paths = {
        "cursor": '<path d="M5 3v28l7-7 6 12 6-3-6-11h11Z"/>',
        "tiles": '<rect x="3" y="3" width="13" height="13" rx="2"/><rect x="23" y="3" width="13" height="13" rx="2"/><rect x="3" y="23" width="13" height="13" rx="2"/><rect x="23" y="23" width="13" height="13" rx="2"/><path d="M16 9h7M9 16v7M30 16v7M16 30h7"/>',
        "shop": '<path d="M4 17h32l-4-12H8L4 17ZM7 22v13h26V22M16 35V23h9v12M4 17v3a4 4 0 0 0 8 0 4 4 0 0 0 8 0 4 4 0 0 0 8 0 4 4 0 0 0 8 0v-3"/>',
        "revive": '<path d="M15 4h10v11h11v10H25v11H15V25H4V15h11Z"/>',
    }
    return f'<g transform="translate({x} {y})" fill="none" stroke="{C[color]}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{paths[kind]}</g>'


def project_card(project):
    color = project["color"]
    body = [frame(432, 202), text(24, 30, project["category"], 10, color, mono=True, spacing=0.6),
            icon(project["icon"], 367, 46, color),
            text(24, 72, project["title"], 23, weight=600, spacing=-0.5)]
    body += [text(24, 105 + i*22, value, 14, "subtext") for i, value in enumerate(project["lines"])]
    body += [line(24, 150, 408, 150), text(24, 180, project["stack"], 11, "muted", mono=True),
             f'<path d="M393 183l12-12m-10 0h10v10" fill="none" stroke="{C[color]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>']
    return svg(432, 214, project["title"], body, " ".join(project["lines"]) + " " + project["stack"])


def activity(data, *, compact=False):
    days = data["days"]
    today = date.fromisoformat(data["updated"])
    total = sum(d["count"] for d in days)
    active = sum(d["count"] > 0 for d in days)
    stars = sum(r["stargazers_count"] for r in data["repos"] if not r["fork"])
    start = date.fromisoformat(days[0]["date"])
    sunday = start - timedelta(days=(start.weekday()+1) % 7)
    width, height = (440, 412) if compact else (880, 326)
    body = [frame(width, height), text(28, 34, "On GitHub", 16, weight=600),
            text(width-28, 33, f"{start:%b %Y} — {today:%b %Y}", 10, "muted", mono=True, anchor="end")]
    for i, (value, label, color) in enumerate([
        (len(data["repos"]), "public repositories", "lavender"),
        (total, "contributions / year", "teal"),
        (active, "active days / year", "peach"),
        (stars, "stars received", "yellow"),
    ]):
        x = 28 + (i % 2)*210 if compact else 28 + i*213
        y = 90 + (i//2)*85 if compact else 90
        body += [text(x, y, f"{value:,}", 37, color, weight=600, spacing=-1),
                 text(x, y+25, label, 12, "muted")]
        if i and not compact:
            body.append(line(x-20, 59, x-20, 117))
    body.append(line(28, 221 if compact else 139, width-28, 221 if compact else 139))
    x0, y0, step, size = (59, 273, 13, 9) if compact else (59, 184, 15, 11)
    if compact:
        body.append(text(28, 246, "Last 26 weeks", 12, "subtext"))
        sunday = today - timedelta(days=(today.weekday()+1) % 7, weeks=25)
    for weekday, label in [(1, "M"), (3, "W"), (5, "F")]:
        body.append(text(31, y0+weekday*step+9, label, 10, "muted", mono=True))
    last_month = None
    heat_colors = ["surface0", "surface2", "overlay", "lavender", "teal"]
    for day in days:
        current = date.fromisoformat(day["date"])
        if current < sunday:
            continue
        offset = (current-sunday).days
        col, row = divmod(offset, 7)
        x, y = x0+col*step, y0+row*step
        if (current.year, current.month) != last_month and (current.day <= 7 or col == 0):
            if col < (24 if compact else 51):
                body.append(text(x, y0-13, f"{current:%b}", 10, "muted", mono=True))
            last_month = (current.year, current.month)
        title = escape(f"{day['date']}: {day['count']} contributions")
        body.append(f'<g><title>{title}</title>{rect(x,y,size,size,heat_colors[day["level"]],2)}</g>')
    footer = height-22
    body += [text(28, footer, f"Updated {today:%d %b %Y}", 9 if compact else 10, "muted", mono=True),
             text(width-184, footer, "less", 10, "muted", mono=True)]
    for i, color in enumerate(heat_colors):
        body.append(rect(width-152+i*15, footer-9, 11, 11, color, 2))
    body.append(text(width-33, footer, "more", 10, "muted", mono=True, anchor="end"))
    return svg(width, height, "GitHub activity", body,
               f"{len(data['repos'])} public repositories. {total} contributions and {active} active days in the last year. {stars} stars received. Updated {data['updated']}.")


def weekly_counts(days, today, count=12):
    this_sunday = today - timedelta(days=(today.weekday()+1) % 7)
    starts = [this_sunday - timedelta(weeks=count-1-i) for i in range(count)]
    totals = Counter()
    for day in days:
        current = date.fromisoformat(day["date"])
        if starts[0] <= current <= today:
            week = (current - starts[0]).days // 7
            totals[week] += day["count"]
    return [(start, totals[i]) for i, start in enumerate(starts)]


def language_groups(languages):
    ordered = Counter(languages).most_common()
    if len(ordered) > 4:
        ordered = ordered[:3] + [("Other", sum(size for _, size in ordered[3:]))]
    total = sum(size for _, size in ordered)
    return [(name, size/total) for name, size in ordered] if total else []


def insights(data, *, compact=False):
    today = date.fromisoformat(data["updated"])
    weeks = weekly_counts(data["days"], today)
    groups = language_groups(data["languages"])
    width, height = (440, 520) if compact else (880, 264)
    body = [frame(width, height), text(28, 34, "Week by week", 16, weight=600),
            text(28, 55, "Contributions · last 12 weeks", 11, "muted"),
            line(28, 264, 412, 264) if compact else line(500, 26, 500, 238)]
    maximum = max(1, max(count for _, count in weeks))
    for ratio in [0, 0.5, 1]:
        y = 190 - ratio*100
        body += [line(54, y, 412 if compact else 470, y, stroke_dasharray="3 5"),
                 text(44, y+4, f"{maximum*ratio:g}", 9, "muted", mono=True, anchor="end")]
    for i, (start, count) in enumerate(weeks):
        x = 62 + i*(29 if compact else 34)
        bar_height = count/maximum*100
        color = "teal" if i == 11 else "lavender"
        body.append(f'<g><title>Week of {start}: {count} contributions</title>'
                    + rect(x, 190-max(bar_height, 2), 19, max(bar_height, 2), color if count else "surface0", 3)
                    + "</g>")
        if count:
            body.append(text(x+9.5, 182-bar_height, count, 10, "muted", mono=True, anchor="middle"))
        if i in [0, 4, 8, 11]:
            label = f"{start:%d %b}" + ("*" if i == 11 else "")
            body.append(text(x+9.5, 211, label, 9, "muted", mono=True, anchor="middle"))
    body.append(text(28, 241, "* current week", 10, "muted", mono=True))
    colors = {"Python": "lavender", "Java": "peach", "JavaScript": "yellow",
              "TypeScript": "blue", "Shell": "green", "Other": "surface2"}
    source = [text(530, 34, "Source mix", 16, weight=600),
              text(530, 55, "Public repos · forks excluded", 11, "muted")]
    cursor = 530
    for i, (name, fraction) in enumerate(groups):
        segment_width = fraction*322
        color = colors.get(name, ["teal", "mauve", "pink", "blue"][i % 4])
        source.append(rect(round(cursor, 2), 80, round(segment_width, 2), 9, color))
        cursor += segment_width
        y = 119+i*28
        source += [rect(530, y-8, 8, 8, color, 2), text(550, y, name, 12, "subtext"),
                 text(852, y, f"{fraction:.1%}", 12, "muted", mono=True, anchor="end")]
    if not groups:
        source.append(text(530, 122, "No detected source languages yet.", 12, "muted"))
    source.append(text(530, 241, "By source bytes, not time spent.", 10, "muted", mono=True))
    body.append(('<g transform="translate(-502 256)">' if compact else '<g>') + "".join(source) + "</g>")
    desc = "; ".join(f"{name}: {fraction:.1%}" for name, fraction in groups)
    return svg(440 if compact else 880, height, "Weekly activity and source languages", body, desc)


def markdown_text(value):
    value = escape(" ".join(value.split()))
    return re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", value)


def project_list(data):
    selected = {p["repo"].lower() for p in PROJECTS}
    rows = []
    for repo in sorted(language_repos(data["repos"]), key=lambda r: r["name"].lower()):
        if repo["name"].lower() in selected:
            continue
        url = f"https://github.com/{USER}/{quote(repo['name'], safe='')}"
        row = f"- [{markdown_text(repo['name'])}]({url})"
        if repo["description"]:
            row += " — " + markdown_text(repo["description"])
        rows.append(row)
    return "\n".join(rows) if rows else "The selected projects above are the current public projects."


def render(data, root=ROOT):
    # Build everything first. A network or parsing failure never replaces a good chart.
    assets = {"header.svg": header(), "activity.svg": activity(data), "insights.svg": insights(data)}
    assets.update({"header-mobile.svg": header(compact=True), "activity-mobile.svg": activity(data, compact=True),
                   "insights-mobile.svg": insights(data, compact=True)})
    assets.update({p["file"]+".svg": project_card(p) for p in PROJECTS})
    readme_path = root / "README.md"
    readme = readme_path.read_text()
    pattern = r"(?<=<!-- PROJECTS:START -->).*?(?=<!-- PROJECTS:END -->)"
    if len(re.findall(pattern, readme, re.S)) != 1:
        raise ValueError("README project markers are missing or ambiguous")
    readme = re.sub(pattern, lambda _: "\n\n"+project_list(data)+"\n\n", readme, flags=re.S)
    (root / "assets").mkdir(exist_ok=True)
    for filename, contents in assets.items():
        (root / "assets" / filename).write_text(contents)
    readme_path.write_text(readme)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-data", type=Path, help="Render a saved public-data snapshot")
    parser.add_argument("--save-data", type=Path, help="Cache public data for offline artwork edits")
    args = parser.parse_args()
    data = json.loads(args.from_data.read_text()) if args.from_data else collect(datetime.now(timezone.utc).date())
    render(data)
    if args.save_data:
        args.save_data.parent.mkdir(parents=True, exist_ok=True)
        args.save_data.write_text(json.dumps(data, indent=2)+"\n")
    print(f"Rendered {len(PROJECTS)+6} SVGs from {len(data['repos'])} public repositories; {data['updated']}.")


if __name__ == "__main__":
    main()
