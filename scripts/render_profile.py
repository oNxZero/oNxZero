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
import xml.etree.ElementTree as ET

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
     "color": "lavender", "logo": "python",
     "lines": ["Record and edit keyboard and mouse input on Linux."],
     "mobile_lines": ["Record and edit keyboard and", "mouse input on Linux."],
     "stack": "Python · Linux · X11 / Wayland"},
    {"repo": "CTM-Gen", "file": "ctm-gen", "title": "CTM Generator",
     "color": "teal", "logo": "python",
     "lines": ["Generate connected texture packs from a block texture."],
     "mobile_lines": ["Generate connected texture packs", "from a block texture."],
     "stack": "Python · Flet · Pillow"},
    {"repo": "spuds-shop-reforged", "file": "spuds-shop-reforged",
     "title": "Spuds Shop Reforged", "color": "peach", "logo": "java",
     "lines": ["Minecraft shop fork with fixes for trades and item duplication."],
     "mobile_lines": ["Minecraft shop fork with fixes", "for trades and item duplication."],
     "stack": "Java · NeoForge · community fork"},
    {"repo": "NotEnoughRevivesReforged", "file": "not-enough-revives",
     "title": "Not Enough Revives Reforged", "color": "green", "logo": "java",
     "lines": ["Minecraft mod for downed players and cooperative revives."],
     "mobile_lines": ["Minecraft mod for downed players", "and cooperative revives."],
     "stack": "Java · NeoForge"},
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


def logo(name, x, y, size):
    # Keep the original, full-color brand artwork; inline it for GitHub's SVG sandbox.
    node = ET.parse(ROOT / "assets" / "logos" / (name+".svg")).getroot()
    node.set("x", str(x)); node.set("y", str(y))
    node.set("width", str(size)); node.set("height", str(size))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(node, encoding="unicode")


def header(*, compact=False):
    width, height = (440, 250) if compact else (880, 220)
    body = [frame(width, height), text(28, 88, USER, 66 if compact else 80, weight=700, spacing=-2)]
    if compact:
        body += [text(28, 139, "making what i need.", 24, "subtext"),
                 text(28, 173, "sometimes releasing it.", 24, "subtext"),
                 text(28, 222, "Linux tools · Minecraft mods", 20, "teal")]
    else:
        body += [text(32, 140, "making what i need. sometimes releasing it.", 27, "subtext"),
                 text(32, 188, "Linux tools · Minecraft mods · small utilities", 23, "teal")]
    for i, color in enumerate(["lavender", "mauve", "pink", "peach", "green", "teal"]):
        body.append(rect(width-130+i*15, 28, 9, 9, color, 2))
    return svg(width, height, USER, body, "making what i need. sometimes releasing it.")


def tools_row(*, compact=False):
    width, height = (440, 180) if compact else (880, 100)
    body = [frame(width, height)]
    for i, (name, label) in enumerate([("python", "Python"), ("java", "Java"), ("linux", "Linux"), ("git", "Git")]):
        x = 28+(i%2)*210 if compact else 32+i*213
        y = 23+(i//2)*80 if compact else 25
        body += [logo(name, x, y, 48), text(x+62, y+33, label, 23, "text", weight=500)]
    return svg(width, height, "Python, Java, Linux and Git", body)


def project_card(project, *, compact=False):
    width, height = (440, 280) if compact else (880, 202)
    body = [frame(width, height), logo(project["logo"], 28, 25, 48)]
    title = project["title"]
    if compact and title == "Not Enough Revives Reforged":
        body += [text(92, 48, "Not Enough Revives", 26, weight=600), text(92, 80, "Reforged", 26, weight=600)]
    else:
        body.append(text(92, 61, title, 26 if compact else 32, weight=600, spacing=-0.4))
    for i, value in enumerate(project["mobile_lines"] if compact else project["lines"]):
        body.append(text(28, (126 if compact else 115)+i*30, value, 22, "subtext"))
    body += [text(28, 234 if compact else 167, project["stack"], 20, "muted")]
    return svg(width, height, title, body, " ".join(project["lines"])+" "+project["stack"])


def activity(data, *, compact=False):
    days = data["days"]
    today = date.fromisoformat(data["updated"])
    total = sum(d["count"] for d in days)
    active = sum(d["count"] > 0 for d in days)
    stars = sum(r["stargazers_count"] for r in data["repos"] if not r["fork"])
    start = date.fromisoformat(days[0]["date"])
    sunday = start - timedelta(days=(start.weekday()+1) % 7)
    width, height = (440, 502) if compact else (880, 430)
    body = [frame(width, height), text(28, 42, "GitHub", 26, weight=600)]
    if not compact:
        body.append(text(width-28, 41, f"{start:%b %Y} — {today:%b %Y}", 20, "muted", anchor="end"))
    for i, (value, label, color) in enumerate([
        (len(data["repos"]), "public repos", "lavender"),
        (total, "contributions / year", "teal"),
        (active, "active days / year", "peach"),
        (stars, "stars received", "yellow"),
    ]):
        x = 28+(i%2)*212 if compact else 28+i*213
        y = 105+(i//2)*106 if compact else 119
        body += [text(x, y, f"{value:,}", 48 if compact else 54, color, weight=600, spacing=-1),
                 text(x, y+33, label, 20, "subtext")]
    divider = 273 if compact else 190
    body += [line(28, divider, width-28, divider),
             text(28, divider+37, "Last 26 weeks" if compact else "Contributions over the last year", 22, "subtext")]
    x0, y0, step, size = (66, 357, 12.5, 9) if compact else (66, 275, 14.7, 11)
    if compact:
        sunday = today-timedelta(days=(today.weekday()+1)%7, weeks=25)
    for weekday, label in [(1, "M"), (3, "W"), (5, "F")]:
        body.append(text(28, y0+weekday*step+10, label, 18, "muted"))
    last_month = None
    heat_colors = ["surface0", "surface2", "overlay", "lavender", "teal"]
    for day in days:
        current = date.fromisoformat(day["date"])
        if current < sunday:
            continue
        col, row = divmod((current-sunday).days, 7)
        if (current.year, current.month) != last_month and (current.day <= 7 or (col == 0 and not compact)):
            if col < (24 if compact else 51):
                body.append(text(round(x0+col*step, 2), y0-17, f"{current:%b}", 18, "muted"))
            last_month = (current.year, current.month)
        title = escape(f"{day['date']}: {day['count']} contributions")
        body.append(f'<g><title>{title}</title>{rect(round(x0+col*step,2),round(y0+row*step,2),size,size,heat_colors[day["level"]],2)}</g>')
    body += [text(28, height-24, f"{today:%d %b %Y}", 18, "muted"),
             text(width-218, height-24, "less", 18, "muted")]
    for i, color in enumerate(heat_colors):
        body.append(rect(width-176+i*17, height-37, 12, 12, color, 2))
    body.append(text(width-28, height-24, "more", 18, "muted", anchor="end"))
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
    width, height = (440, 350) if compact else (880, 340)
    body = [frame(width, height), text(28, 43, "Weekly contributions", 26, weight=600),
            text(28, 76, "Last 12 weeks", 20, "muted")]
    maximum = max(1, max(count for _, count in weeks))
    chart_top, chart_bottom = 133, 253
    # Use fewer labels on narrow screens, with the same underlying weekly data.
    for ratio in [0, 0.5, 1]:
        y = chart_bottom-ratio*(chart_bottom-chart_top)
        body += [line(64, y, width-28, y, stroke_dasharray="3 5"),
                 text(55, y+6, f"{maximum*ratio:g}", 18, "muted", anchor="end")]
    gap = (width-112)/12
    bar_width = 19 if compact else 40
    for i, (start, count) in enumerate(weeks):
        x = 76+i*gap
        bar_height = count/maximum*(chart_bottom-chart_top)
        color = "teal" if i == 11 else "lavender"
        body.append(f'<g><title>Week of {start}: {count} contributions</title>'
                    + rect(round(x,2), round(chart_bottom-max(bar_height,2),2), bar_width, round(max(bar_height,2),2), color if count else "surface0", 3)+"</g>")
        if count and not compact:
            body.append(text(round(x+bar_width/2,2), round(chart_bottom-bar_height-12,2), count, 20, "subtext", anchor="middle"))
        if i in [0, 4, 8] or (not compact and i == 11):
            body.append(text(round(x+bar_width/2,2), chart_bottom+31, f"{start:%d %b}", 18, "muted", anchor="middle"))
    body.append(text(28, height-22, "The current week is still in progress.", 18, "muted"))
    return svg(width, height, "Weekly GitHub contributions", body)


def languages(data, *, compact=False):
    groups = language_groups(data["languages"])
    width, height = (440, 360) if compact else (880, 324)
    body = [frame(width, height), text(28, 43, "Languages", 26, weight=600),
            text(28, 77, "Source in public repos · forks excluded", 20, "muted")]
    colors = {"Python": "lavender", "Java": "peach", "JavaScript": "yellow",
              "TypeScript": "blue", "Shell": "green", "Other": "surface2"}
    cursor = 28
    for i, (name, fraction) in enumerate(groups):
        color = colors.get(name, ["teal", "mauve", "pink", "blue"][i%4])
        body.append(rect(round(cursor,2), 104, round(fraction*(width-56),2), 14, color))
        cursor += fraction*(width-56)
        y = 158+i*40
        if name.lower() in {"python", "java"}:
            body.append(logo(name.lower(), 28, y-23, 30))
        else:
            body.append(rect(36, y-14, 12, 12, color, 2))
        body += [text(72, y, name, 22, "subtext"),
                 text(width-28, y, f"{fraction:.1%}", 22, "text", anchor="end")]
    if not groups:
        body.append(text(28, 160, "No detected source languages yet.", 22, "subtext"))
    return svg(width, height, "Languages by source bytes", body,
               "; ".join(f"{name}: {fraction:.1%}" for name, fraction in groups))


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
    assets = {"header.svg": header(), "activity.svg": activity(data), "insights.svg": insights(data),
              "languages.svg": languages(data), "tools.svg": tools_row()}
    assets.update({"header-mobile.svg": header(compact=True), "activity-mobile.svg": activity(data, compact=True),
                   "insights-mobile.svg": insights(data, compact=True), "languages-mobile.svg": languages(data, compact=True),
                   "tools-mobile.svg": tools_row(compact=True)})
    assets.update({p["file"]+".svg": project_card(p) for p in PROJECTS})
    assets.update({p["file"]+"-mobile.svg": project_card(p, compact=True) for p in PROJECTS})
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
    print(f"Rendered {len(PROJECTS)*2+10} SVGs from {len(data['repos'])} public repositories; {data['updated']}.")


if __name__ == "__main__":
    main()
