#!/usr/bin/env python3
"""Render the profile from GitHub activity and aggregate repository totals."""

import argparse
from collections import Counter
import base64
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from functools import lru_cache
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
    {"repo": "CTM-Gen", "file": "ctm-gen", "title": "CTM Generator",
     "color": "teal", "logo": "python", "project_logo": "ctm-gen.png",
     "lines": ["Generate connected texture packs from a block texture."],
     "mobile_lines": ["Generate connected texture packs", "from a block texture."],
     "stack": "Python · Flet · Pillow"},
    {"repo": "Moonlight", "file": "moonlight", "title": "Moonlight",
     "color": "mauve", "logo": "python", "project_logo": "moonlight.svg",
     "lines": ["Linux auto-clicker with adjustable timing and presets."],
     "mobile_lines": ["Auto-clicking on Linux with", "adjustable timing and presets."],
     "stack": "Python · GTK · Linux"},
    {"repo": "Automater", "file": "automater", "title": "Automater",
     "color": "lavender", "logo": "python", "project_logo": "automater.svg",
     "lines": ["Record and edit keyboard and mouse input on Linux."],
     "mobile_lines": ["Record keyboard and mouse input.", "Edit and replay it on Linux."],
     "stack": "Python · Qt · Linux"},
    {"repo": "spuds-shop-reforged", "file": "spuds-shop-reforged",
     "title": "Spuds Shop Reforged", "color": "peach", "logo": "java", "project_logo": "spuds-shop-reforged.png",
     "lines": ["Minecraft shop fork with fixes for trades and item duplication."],
     "mobile_lines": ["Minecraft shop fork with fixes", "for trades and item duplication."],
     "stack": "Java · NeoForge · fork"},
]
SKILLS = [
    ("python", "Python", "https://www.python.org/"),
    ("java", "Java", "https://dev.java/"),
    ("javascript", "JavaScript", "https://tc39.es/ecma262/"),
    ("typescript", "TypeScript", "https://www.typescriptlang.org/"),
    ("vuejs", "Vue", "https://vuejs.org/"),
    ("nodejs", "Node.js", "https://nodejs.org/"),
    ("qt", "Qt", "https://www.qt.io/"),
    ("react", "React", "https://react.dev/"),
    ("mysql", "MySQL", "https://www.mysql.com/"),
    ("docker", "Docker", "https://www.docker.com/"),
    ("linux", "Linux", "https://www.kernel.org/"),
    ("git", "Git", "https://git-scm.com/"),
]


def request(url, *, api=False, token=None):
    headers = {"User-Agent": f"{USER}-profile", "Accept-Language": "en-US,en;q=0.9"}
    if api:
        if not url.startswith("https://api.github.com/"):
            raise ValueError("API credentials may only be sent to api.github.com")
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        token = token or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
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


def api(path, *, token=None):
    return json.loads(request(f"https://api.github.com{path}", api=True, token=token))


def read_private_totals(path=None):
    path = path or ROOT / "data" / "private-totals.json"
    totals = json.loads(path.read_text())
    if set(totals) != {"updated", "repository_count", "stars_received"}:
        raise ValueError("Private totals must contain aggregate counts and a date only")
    date.fromisoformat(totals["updated"])
    for key in ["repository_count", "stars_received"]:
        if type(totals[key]) is not int or totals[key] < 0:
            raise ValueError("Private repository totals must be nonnegative integers")
    return totals


def refresh_private_totals(today):
    token = os.environ.get("PROFILE_STATS_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ValueError("Refreshing private totals requires an authenticated GitHub token")
    viewer = api("/user", token=token)
    if viewer.get("login", "").lower() != USER.lower():
        raise ValueError("Private stats token must belong to the profile owner")
    repos = []
    page = 1
    while True:
        batch = api(f"/user/repos?visibility=private&affiliation=owner&per_page=100&page={page}", token=token)
        if not isinstance(batch, list):
            raise ValueError("Unexpected private repository response")
        repos.extend(r for r in batch if r.get("private") is True
                     and r.get("owner", {}).get("login", "").lower() == USER.lower())
        if len(batch) < 100:
            break
        page += 1
    expected = viewer.get("owned_private_repos")
    if expected is not None and expected != len(repos):
        raise ValueError("Token cannot see every owned private repository; keeping the current snapshot")
    totals = {"updated": today.isoformat(), "repository_count": len(repos),
              "stars_received": sum(r["stargazers_count"] for r in repos if not r["fork"])}
    target = ROOT / "data" / "private-totals.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(totals, indent=2)+"\n")
    return totals


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


def public_project_repos(repos):
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
    return {
        "updated": today.isoformat(), "days": days,
        "repos": [{k: r[k] for k in ("name", "description", "html_url", "private", "fork",
                                    "archived", "stargazers_count", "language")} for r in repos],
        "private_totals": read_private_totals(),
    }


def rect(x, y, w, h, fill, radius=0, **attrs):
    extra = " ".join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{C.get(fill, fill)}" {extra}/>'


@lru_cache(maxsize=1)
def font_atlas():
    return json.loads((ROOT / "assets" / "fonts" / "atlas.json").read_text())


def text(x, y, value, size=14, color="text", *, mono=False, weight=400, anchor="start", spacing=0):
    value = str(value)
    style = ("mono-medium" if mono or re.fullmatch(r"[\d,.%]+", value)
             else "sans-bold" if weight >= 700 else "sans-semibold" if weight >= 500 else "sans-regular")
    font = font_atlas()[style]
    scale = size/font["units"]
    positions = []
    cursor = 0
    for character in value:
        character = character if character in font["glyphs"] else "?"
        glyph = font["glyphs"][character]
        if glyph["path"]:
            positions.append(f'<use href="#glyph-{style}-{ord(character):04x}" x="{round(cursor,2)}"/>')
        cursor += glyph["advance"]+spacing/scale
    width = (cursor-spacing/scale)*scale if value else 0
    origin = x-width/2 if anchor == "middle" else x-width if anchor == "end" else x
    return (f'<g aria-label="{escape(value, quote=True)}" data-label="{escape(value, quote=True)}" '
            f'data-font="{font["family"]}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{C.get(color,color)}" transform="translate({round(origin,3)} {y}) scale({scale} {-scale})">'
            +"".join(positions)+"</g>")


def line(x1, y1, x2, y2, color="surface0", **attrs):
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C[color]}" {extra}/>'


def svg(width, height, title, body, description=""):
    content = "\n".join(body)
    glyphs = sorted(set(re.findall(r'href="#glyph-([a-z-]+)-([0-9a-f]+)"', content)))
    outlines = [f'<path id="glyph-{style}-{code}" d="{font_atlas()[style]["glyphs"][chr(int(code,16))]["path"]}"/>'
                for style,code in glyphs]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
            f'<title id="title">{escape(title)}</title>\n<desc id="desc">{escape(description or title)}</desc>\n'
            + "<defs>"+"".join(outlines)+"</defs>\n"+content + "\n</svg>\n")


def frame(width, height):
    shadow = ('<defs><filter id="panel-shadow" x="-10%" y="-10%" width="120%" height="130%">'
              '<feDropShadow dx="0" dy="5" stdDeviation="4" flood-color="#181926" flood-opacity="0.7"/>'
              '</filter></defs>')
    return shadow + rect(4, 2, width-12, height-14, "base", 14, stroke=C["surface1"],
                         stroke_width=1.5, filter="url(#panel-shadow)")


def logo(name, x, y, size):
    # Keep the original, full-color brand artwork; inline it for GitHub's SVG sandbox.
    node = ET.parse(ROOT / "assets" / "logos" / (name+".svg")).getroot()
    node.set("x", str(x)); node.set("y", str(y))
    node.set("width", str(size)); node.set("height", str(size))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(node, encoding="unicode")


def ui_icon(name, x, y, size, color="muted"):
    node = ET.parse(ROOT / "assets" / "icons" / (name+".svg")).getroot()
    for key,value in {"x":x,"y":y,"width":size,"height":size,"stroke":C[color]}.items():
        node.set(key,str(value))
    return ET.tostring(node, encoding="unicode")


def header(*, compact=False):
    width, height = (440, 250) if compact else (880, 220)
    center = width/2-2
    body = [frame(width, height), text(center, 88, USER, 66 if compact else 80, weight=700, spacing=-2, anchor="middle")]
    if compact:
        body += [text(center, 139, "making what i need.", 24, "subtext", anchor="middle"),
                 text(center, 173, "sometimes releasing it.", 24, "subtext", anchor="middle"),
                 text(center, 222, "Linux tools · Minecraft mods", 20, "teal", anchor="middle")]
    else:
        body += [text(center, 140, "making what i need. sometimes releasing it.", 27, "subtext", anchor="middle"),
                 text(center, 188, "Linux tools · Minecraft mods · small utilities", 23, "teal", anchor="middle")]
    for i, color in enumerate(["lavender", "mauve", "pink", "peach", "green", "teal"]):
        body.append(rect(width-(166 if compact else 176)+i*(22 if compact else 25),
                         18 if compact else 26, 14 if compact else 16,
                         14 if compact else 16, color, 3))
    return svg(width, height, USER, body, "making what i need. sometimes releasing it.")


def skill_card(name, label):
    body = [frame(140, 120)]
    if name == "mysql":
        body.append(rect(44, 14, 52, 52, "text", 10))
    body += [logo(name, 46, 16, 48), text(70, 95, label, 20, "text", anchor="middle", weight=500)]
    return svg(140, 120, label, body, f"Open the official {label} site")


def project_mark(project, x, y, size):
    filename = project.get("project_logo")
    if not filename:
        return logo(project["logo"], x, y, size)
    path = ROOT / "assets" / "project-logos" / filename
    if path.suffix == ".svg":
        node = ET.parse(path).getroot()
        node.set("x", str(x)); node.set("y", str(y))
        node.set("width", str(size)); node.set("height", str(size))
        return ET.tostring(node, encoding="unicode")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/gif" if path.suffix == ".gif" else "image/png"
    return f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:{mime};base64,{encoded}"/>'


def project_card(project, *, compact=False):
    width, height = 432, 224
    body = [frame(width, height), project_mark(project, 24, 17, 64)]
    title = project["title"]
    if title == "Not Enough Revives Reforged":
        body += [text(104, 43, "Not Enough Revives", 26, weight=600), text(104, 73, "Reforged", 26, weight=600)]
    elif title == "Spuds Shop Reforged":
        body += [text(104, 43, "Spuds Shop", 28, weight=600), text(104, 73, "Reforged", 28, weight=600)]
    else:
        body.append(text(104, 58, title, 28, weight=600, spacing=-0.4))
    for i, value in enumerate(project["mobile_lines"]):
        body.append(text(28, 112+i*28, value, 22, "subtext"))
    body += [logo(project["logo"], 28, 171, 25), text(65, 192, project["stack"], 20, "muted", mono=True),
             ui_icon("arrow-up-right",366,170,29,project["color"])]
    return svg(width, height, title, body, " ".join(project["lines"])+" "+project["stack"])


def activity(data, *, compact=False):
    days = data["days"]
    today = date.fromisoformat(data["updated"])
    total = sum(d["count"] for d in days)
    active = sum(d["count"] > 0 for d in days)
    private = data.get("private_totals", {"repository_count": 0, "stars_received": 0})
    repository_count = len(data["repos"])+private["repository_count"]
    stars = sum(r["stargazers_count"] for r in data["repos"] if not r["fork"])+private["stars_received"]
    start = date.fromisoformat(days[0]["date"])
    sunday = start - timedelta(days=(start.weekday()+1) % 7)
    width, height = (440, 536) if compact else (880, 430)
    body = [frame(width, height), rect(26,17,34,34,"text",9), logo("github",29,20,28),
            text(72, 42, "GitHub", 26, weight=600),
            text(184, 42, "Public + private", 20, "muted")]
    if compact:
        body.append(text(28, 73, f"{start:%b %Y} → {today:%b %Y}", 20, "muted"))
    else:
        body.append(text(width-28, 41, f"{start:%b %Y} → {today:%b %Y}", 20, "muted", anchor="end"))
    for i, (value, label, color) in enumerate([
        (repository_count, "repositories", "lavender"),
        (total, "contributions / year", "teal"),
        (active, "active days / year", "peach"),
        (stars, "stars received", "yellow"),
    ]):
        x = 28+(i%2)*212 if compact else 28+i*213
        y = 137+(i//2)*106 if compact else 119
        body += [text(x, y, f"{value:,}", 48 if compact else 54, color, weight=600, spacing=-1),
                 text(x, y+33, label.replace(" / year", " / yr") if compact else label, 20, "subtext")]
    divider = 311 if compact else 190
    body += [line(28, divider, width-28, divider),
             text(28, divider+37, "Last 26 weeks" if compact else "Contributions over the last year", 22, "subtext")]
    x0, y0, step, size = (66, 395, 12.5, 10) if compact else (66, 275, 14.7, 12)
    if compact:
        sunday = today-timedelta(days=(today.weekday()+1)%7, weeks=25)
    for weekday, label in [(1, "M"), (3, "W"), (5, "F")]:
        body.append(text(28, y0+weekday*step+10, label, 18, "muted"))
    last_month = None
    heat_colors = ["mantle", "blue", "lavender", "teal", "green"]
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
        body.append(f'<g><title>{title}</title>{rect(round(x0+col*step,2),round(y0+row*step,2),size,size,heat_colors[day["level"]],2,stroke=C["surface0"] if day["level"]==0 else C[heat_colors[day["level"]]],stroke_width=0.6)}</g>')
    body += [text(28, height-24, f"{today:%d %b %Y}", 18, "muted"),
             text(width-218, height-24, "less", 18, "muted")]
    for i, color in enumerate(heat_colors):
        body.append(rect(width-176+i*17, height-37, 12, 12, color, 2))
    body.append(text(width-28, height-24, "more", 18, "muted", anchor="end"))
    return svg(width, height, "GitHub activity", body,
               f"{repository_count} public and private repositories. {total} contributions and {active} active days in the last year. {stars} stars received. Updated {data['updated']}.")


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



def insights(data, *, compact=False):
    today = date.fromisoformat(data["updated"])
    weeks = weekly_counts(data["days"], today)
    width, height = (440, 370) if compact else (880, 370)
    period_total = sum(count for _, count in weeks)
    body = [frame(width, height), ui_icon("chart-spline",28,23,25,"teal"),
            text(66, 43, "Weekly contributions", 26, weight=600),
            text(28, 77, "Last 12 weeks", 20, "muted")]
    if not compact:
        body += [text(width-28, 45, f"{period_total:,}", 34, "teal", weight=600, anchor="end"),
                 text(width-28, 76, "12-week total", 18, "muted", anchor="end")]
    else:
        body.append(text(width-28, 77, f"{period_total:,} total", 20, "teal", anchor="end"))
    maximum = max(1, max(count for _, count in weeks))
    top, bottom, left, right = 138, 280, 68, width-42
    points = [(round(left+i*(right-left)/11,2), round(bottom-count/maximum*(bottom-top),2))
              for i, (_,count) in enumerate(weeks)]
    for ratio in [0, 0.5, 1]:
        y = bottom-ratio*(bottom-top)
        body += [line(left, y, right, y, stroke_dasharray="3 6"),
                 text(left-13, y+6, f"{maximum*ratio:g}", 18, "muted", anchor="end")]

    def curve(vertices):
        result = f"M{vertices[0][0]} {vertices[0][1]}"
        for (x1,y1),(x2,y2) in zip(vertices,vertices[1:]):
            control = (x2-x1)*0.4
            result += f" C{round(x1+control,2)} {y1} {round(x2-control,2)} {y2} {x2} {y2}"
        return result

    body += ['<defs><linearGradient id="weekly-area" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0%" stop-color="{C["lavender"]}" stop-opacity="0.28"/>'
             f'<stop offset="100%" stop-color="{C["lavender"]}" stop-opacity="0.02"/>'
             '</linearGradient></defs>',
             f'<path d="{curve(points)} L{right} {bottom} L{left} {bottom} Z" fill="url(#weekly-area)"/>',
             f'<path d="{curve(points[:-1])}" fill="none" stroke="{C["lavender"]}" stroke-width="3" stroke-linecap="round"/>',
             f'<path d="{curve(points[-2:])}" fill="none" stroke="{C["teal"]}" stroke-width="3" stroke-dasharray="5 5" stroke-linecap="round"/>']
    peak = max(range(len(weeks)), key=lambda i: weeks[i][1])
    for i, ((start,count),(x,y)) in enumerate(zip(weeks,points)):
        color = "teal" if i==11 else "peach" if i==peak else "lavender"
        if i==11:
            body.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{C[color]}" fill-opacity="0.16"/>')
        body.append(f'<g><title>Week of {start}: {count} contributions</title>'
                    f'<circle cx="{x}" cy="{y}" r="4.5" fill="{C[color]}" stroke="{C["base"]}" stroke-width="2"/></g>')
        if count and (not compact or i in [peak,11]):
            body.append(text(x, y-16, count, 20, color if i in [peak,11] else "subtext", anchor="middle"))
        if i in [0,4,8] or (not compact and i==11):
            body.append(text(x, bottom+31, f"{start:%d %b}", 18, "muted", anchor="middle"))
    body += [rect(28,height-38,9,9,"teal",4),
             text(47,height-29,"Current week in progress",18,"muted")]
    return svg(width,height,"Weekly GitHub contributions",body,
               f"{period_total} contributions over the last twelve weeks. Current week is incomplete.")



def markdown_text(value):
    value = escape(" ".join(value.split()))
    return re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", value)


def project_list(data):
    selected = {p["repo"].lower() for p in PROJECTS}
    rows = []
    for repo in sorted(public_project_repos(data["repos"]), key=lambda r: r["name"].lower()):
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
    assets = {"header-palette.svg": header(), "activity-bright.svg": activity(data), "weekly-trend.svg": insights(data),
              "header-palette-mobile.svg": header(compact=True),
              "activity-bright-mobile.svg": activity(data, compact=True),
              "weekly-trend-mobile.svg": insights(data, compact=True)}
    assets.update({p["file"]+"-compact.svg": project_card(p) for p in PROJECTS})
    assets.update({"skill-"+name+".svg": skill_card(name, label) for name, label, _ in SKILLS})
    readme_path = root / "README.md"
    readme = readme_path.read_text()
    pattern = r"(?<=<!-- PROJECTS:START -->).*?(?=<!-- PROJECTS:END -->)"
    if len(re.findall(pattern, readme, re.S)) != 1:
        raise ValueError("README project markers are missing or ambiguous")
    readme = re.sub(pattern, lambda _: "\n\n"+project_list(data)+"\n\n", readme, flags=re.S)
    artwork = root / "assets" / "profile-v5"
    artwork.mkdir(parents=True, exist_ok=True)
    for filename, contents in assets.items():
        (artwork / filename).write_text(contents)
    readme_path.write_text(readme)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-data", type=Path, help="Render a saved public-data snapshot")
    parser.add_argument("--save-data", type=Path, help="Cache public data for offline artwork edits")
    parser.add_argument("--refresh-private", action="store_true", help="Refresh aggregate private totals using an authenticated owner token")
    args = parser.parse_args()
    if args.refresh_private or os.environ.get("PROFILE_STATS_TOKEN"):
        refresh_private_totals(datetime.now(timezone.utc).date())
    data = json.loads(args.from_data.read_text()) if args.from_data else collect(datetime.now(timezone.utc).date())
    render(data)
    if args.save_data:
        args.save_data.parent.mkdir(parents=True, exist_ok=True)
        args.save_data.write_text(json.dumps(data, indent=2)+"\n")
    print(f"Rendered {len(PROJECTS)+len(SKILLS)+6} SVGs from {len(data['repos'])} public repositories; {data['updated']}.")


if __name__ == "__main__":
    main()
