"""Generate a neofetch-style profile card (dark_mode.svg / light_mode.svg).

Left side: ASCII art made from your GitHub avatar.
Right side: the INFO / CONTACT lines below plus live GitHub stats.

Run locally:  python profile/generate.py
In Actions, GITHUB_TOKEN is used so the commit count can be fetched.
"""

import io
import json
import os
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# ----------------------------------------------------------------------------
# Edit these to change what the card says.
# ----------------------------------------------------------------------------
USERNAME = os.environ.get("GH_USERNAME", "LucasKimo")
HEADER = "lucas@kim"

INFO = [
    ("Role", "Software Engineer"),
    ("Focus", "AI Engineering, Full-stack Development"),
    ("Education", "Queensland University of Technology"),
    ("IDE", "VS Code, Jupyter"),
    None,  # blank line
    ("Languages.Programming", "Python, TypeScript, JavaScript, Java"),
    ("Languages.Computer", "HTML, CSS, SQL, JSON, YAML"),
    None,
    ("AI.Stack", "PyTorch, LangChain, Hugging Face"),
    ("Web.Stack", "React, Node.js, FastAPI"),
    ("Cloud", "Azure, AWS, Docker"),
]

CONTACT = [
    ("Email", "contact@lucaskim.dev"),
    ("LinkedIn", "lucas-eunsu-kim"),
]

# ----------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------
LINE_H = 20          # px between lines
CHAR_W = 9.6         # approx width of one 16px monospace character
TEXT_COLS = 62       # width of each right-hand line in characters
ART_COLS = 40        # width of the art area, measured in 16px characters
ART_SCALE = 2.5      # art uses a smaller font: 2.5x more columns and rows
ART_FONT = 16 / ART_SCALE
ART_LINE_H = LINE_H / ART_SCALE
ART_W = ART_COLS * CHAR_W  # art area width in px
# dim -> dense; a long ramp gives smoother shading
RAMP = (" .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$")
ART_CONTRAST = 1.4   # >1 = punchier face, 1 = original
ART_SHARPEN = 160    # unsharp mask strength (percent); 0 = off

THEMES = {
    "dark": {"bg": "#161b22", "fg": "#c9d1d9", "key": "#ffa657",
             "value": "#a5d6ff", "dots": "#616e7f"},
    "light": {"bg": "#f6f8fa", "fg": "#24292f", "key": "#953800",
              "value": "#0a3069", "dots": "#c2cfde"},
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ----------------------------------------------------------------------------
# GitHub data
# ----------------------------------------------------------------------------
def _request(url, data=None):
    headers = {"User-Agent": "profile-card-generator",
               "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def get_stats():
    user = json.loads(_request(f"https://api.github.com/users/{USERNAME}"))
    stars, page = 0, 1
    while True:
        repos = json.loads(_request(
            f"https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}"))
        stars += sum(r["stargazers_count"] for r in repos)
        if len(repos) < 100:
            break
        page += 1

    commits = None
    if os.environ.get("GITHUB_TOKEN"):
        start = int(user["created_at"][:4])
        parts = [
            f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", '
            f'to: "{y}-12-31T23:59:59Z") {{ totalCommitContributions }}'
            for y in range(start, datetime.now(timezone.utc).year + 1)
        ]
        query = f'query {{ user(login: "{USERNAME}") {{ {" ".join(parts)} }} }}'
        body = json.dumps({"query": query}).encode()
        data = json.loads(_request("https://api.github.com/graphql", body))
        commits = sum(v["totalCommitContributions"]
                      for v in data["data"]["user"].values())

    return {
        "Repos": user["public_repos"],
        "Stars": stars,
        "Followers": user["followers"],
        "Commits": commits,
    }


def get_ascii(rows):
    """Return {'dark': [...], 'light': [...]} ASCII lines for the avatar."""
    raw = _request(f"https://github.com/{USERNAME}.png?size=460")
    img = Image.open(io.BytesIO(raw)).convert("L")
    cols = round(ART_COLS * ART_SCALE)
    art_rows = round(rows * ART_SCALE)
    # Crop to the same aspect ratio as the ASCII block.
    target = ART_W / (rows * LINE_H)
    img = ImageOps.fit(img, (int(img.height * target), img.height))
    # Bring out facial detail before shrinking.
    img = ImageOps.autocontrast(img, cutoff=1)
    if ART_SHARPEN:
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=ART_SHARPEN))
    img = ImageEnhance.Contrast(img).enhance(ART_CONTRAST)
    img = img.resize((cols, art_rows), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=0.5)
    n = len(RAMP)
    out = {}
    for theme, invert in (("dark", False), ("light", True)):
        lines = []
        for r in range(art_rows):
            line = ""
            for c in range(cols):
                v = img.getpixel((c, r)) / 255
                if invert:
                    v = 1 - v
                line += RAMP[min(int(v * n), n - 1)]
            lines.append(line)
        out[theme] = lines
    return out


# ----------------------------------------------------------------------------
# SVG
# ----------------------------------------------------------------------------
def kv_line(key, value):
    """'. Key: ..... value' padded to TEXT_COLS characters."""
    key_parts = key.split(".")
    key_len = len(key) + 1  # +1 for ':'
    dots = max(TEXT_COLS - 2 - key_len - len(value) - 2, 1)
    keys = '</tspan>.<tspan class="key">'.join(escape(k) for k in key_parts)
    return (f'<tspan class="dots">. </tspan><tspan class="key">{keys}</tspan>:'
            f'<tspan class="dots"> {"." * dots} </tspan>'
            f'<tspan class="value">{escape(value)}</tspan>')


def header_line(title):
    return f'{escape(title)} -{"—" * (TEXT_COLS - len(title) - 2)}'


def build_lines(stats):
    lines = [header_line(HEADER)]
    for item in INFO:
        lines.append('<tspan class="dots">. </tspan>' if item is None
                     else kv_line(*item))
    lines.append("")
    lines.append(header_line("- Contact"))
    lines += [kv_line(k, v) for k, v in CONTACT]
    lines.append("")
    lines.append(header_line("- GitHub Stats"))
    fmt = lambda n: "—" if n is None else f"{n:,}"
    lines.append(kv_line("Repos", fmt(stats["Repos"])))
    lines.append(kv_line("Stars", fmt(stats["Stars"])))
    lines.append(kv_line("Commits", fmt(stats["Commits"])))
    lines.append(kv_line("Followers", fmt(stats["Followers"])))
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines.append(kv_line("Last.Updated", updated))
    return lines


def render(theme, art, lines):
    t = THEMES[theme]
    rows = len(lines)
    text_x = 15 + int(ART_W) + 25
    width = text_x + int(TEXT_COLS * CHAR_W) + 15
    height = rows * LINE_H + 25
    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Consolas,Menlo,\'DejaVu Sans Mono\',monospace" '
        f'width="{width}px" height="{height}px" font-size="16px">',
        "<style>",
        f".key {{fill: {t['key']};}}",
        f".value {{fill: {t['value']};}}",
        f".dots {{fill: {t['dots']};}}",
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{width}px" height="{height}px" fill="{t["bg"]}" rx="15"/>',
        f'<text x="15" y="30" fill="{t["fg"]}" font-size="{ART_FONT:g}px">',
    ]
    # textLength pins every art line to the same width whatever font loads.
    top = 30 - 0.75 * (16 - ART_FONT)  # align art top with the first text line
    for i, line in enumerate(art):
        y = top + i * ART_LINE_H
        out.append(f'<tspan x="15" y="{y:.1f}" textLength="{ART_W:.0f}" '
                   f'lengthAdjust="spacingAndGlyphs">{escape(line)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{text_x}" y="30" fill="{t["fg"]}">')
    for i, line in enumerate(lines):
        out.append(f'<tspan x="{text_x}" y="{30 + i * LINE_H}">{line}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    try:
        stats = get_stats()
    except Exception as e:  # keep the card building even if the API hiccups
        print(f"Could not fetch stats: {e}")
        stats = {"Repos": None, "Stars": None, "Followers": None, "Commits": None}
    lines = build_lines(stats)
    art = get_ascii(len(lines))
    for theme in THEMES:
        path = os.path.join(ROOT, f"{theme}_mode.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(theme, art[theme], lines))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
