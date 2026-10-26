"""Fetch AI news feeds and render a static site to docs/index.html."""
import html, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import feedparser

FEEDS = {
    "TechCrunch": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "VentureBeat": "https://venturebeat.com/category/ai/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "Ars Technica": "https://arstechnica.com/ai/feed/",
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
}
TZ = ZoneInfo("America/Toronto")
MAX_AGE_DAYS, MAX_ITEMS, SUMMARY_CHARS = 4, 80, 200


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def shorten(text, n=SUMMARY_CHARS):
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def fetch():
    items, seen = [], set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url, agent="ai-news-digest/1.0")
        except Exception as exc:
            print(f"skip {source}: {exc}", file=sys.stderr)
            continue
        if not feed.entries:
            print(f"no entries from {source}", file=sys.stderr)
        for e in feed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            link, title = e.get("link", ""), clean(e.get("title"))
            if not ts or not title or not link.startswith(("http://", "https://")):
                continue
            when = datetime(*ts[:6], tzinfo=timezone.utc)
            key = re.sub(r"\W+", "", title.lower())
            if when < cutoff or when > now + timedelta(days=1) or key in seen:
                continue
            seen.add(key)
            summary = shorten(clean(e.get("summary")))
            if summary.lower().startswith(title.lower()[:30]):
                summary = ""
            items.append(dict(source=source, title=title, link=link, summary=summary, when=when.astimezone(TZ)))
    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:MAX_ITEMS]


def render(items):
    esc = html.escape
    today = datetime.now(TZ).date()
    body, day = [], None
    for it in items:
        d = it["when"].date()
        if d != day:
            if day:
                body.append("</ol></section>")
            day = d
            label = "Today" if d == today else "Yesterday" if d == today - timedelta(days=1) else d.strftime("%A, %B %-d")
            body.append(f'<section><h2>{label}</h2><ol>')
        body.append(
            f'<li><div class="meta"><span class="src">{esc(it["source"])}</span>'
            f'<time datetime="{it["when"].isoformat()}">{it["when"].strftime("%-I:%M %p")}</time></div>'
            f'<div><a href="{esc(it["link"])}" rel="noopener">{esc(it["title"])}</a>'
            + (f'<p>{esc(it["summary"])}</p>' if it["summary"] else "")
            + "</div></li>"
        )
    if day:
        body.append("</ol></section>")
    if not body:
        body.append("<p class='empty'>No stories could be loaded. The next scheduled update will try again.</p>")
    stamp = datetime.now(TZ).strftime("%B %-d, %-I:%M %p %Z")
    return PAGE.replace("{{STAMP}}", stamp).replace("{{COUNT}}", str(len(items))).replace("{{BODY}}", "\n".join(body))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI News</title>
<meta name="description" content="AI headlines from leading sources, updated twice a day.">
<style>
:root{--bg:#f3f5f8;--ink:#141a24;--mute:#5a6578;--line:#d5dbe5;--link:#1f3fd6;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--bg:#10141c;--ink:#e8ecf3;--mute:#93a0b6;--line:#2a3344;--link:#8da2ff;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
main{max-width:780px;margin:0 auto;padding:48px 20px 80px}
header{border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:8px}
h1{font:700 clamp(40px,9vw,72px)/1 "Iowan Old Style",Palatino,Georgia,serif;letter-spacing:-.02em;margin:0 0 12px}
.status{margin:0;color:var(--mute);font-size:14px}
h2{font:600 15px/1 system-ui,sans-serif;color:var(--mute);margin:36px 0 4px}
ol{list-style:none;margin:0;padding:0}
li{display:grid;grid-template-columns:150px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid var(--line)}
.meta{display:flex;flex-direction:column;font-size:13px;color:var(--mute)}
.src{font-weight:600;color:var(--ink)}
a{font:600 19px/1.3 "Iowan Old Style",Palatino,Georgia,serif;color:var(--ink);text-decoration:none}
a:hover{color:var(--link);text-decoration:underline}
a:focus-visible{outline:2px solid var(--link);outline-offset:3px}
p{margin:6px 0 0;color:var(--mute);font-size:15px;max-width:62ch}
.empty{margin-top:32px}
@media(max-width:560px){li{grid-template-columns:1fr;gap:4px}.meta{flex-direction:row;gap:10px}}
</style></head><body><main>
<header><h1>AI News</h1>
<p class="status">Updated {{STAMP}}. {{COUNT}} stories from the last few days. Refreshes twice a day.</p></header>
{{BODY}}
</main></body></html>
"""

if __name__ == "__main__":
    out = Path(__file__).parent / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(render(fetch()), encoding="utf-8")
    print("wrote", out / "index.html")
