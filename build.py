"""Fetch AI news feeds and render a static site to docs/index.html."""
import html, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import feedparser

FEEDS = {
    "TechCrunch": "https://techcrunch.com/category/artificial-intelligence/feed/",
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


def find_image(e):
    """Best-effort thumbnail from feed metadata; https only."""
    for key in ("media_thumbnail", "media_content"):
        for m in e.get(key) or []:
            u = m.get("url", "")
            if u.startswith("https://") and (key == "media_thumbnail" or m.get("medium") == "image" or m.get("type", "").startswith("image")):
                return u
    for l in e.get("links") or []:
        if l.get("rel") == "enclosure" and l.get("type", "").startswith("image") and l.get("href", "").startswith("https://"):
            return l["href"]
    blob = " ".join([e.get("summary") or ""] + [c.get("value", "") for c in e.get("content") or []])
    m = re.search(r"<img[^>]+src=[\"'](https://[^\"']+)", blob)
    return m.group(1) if m else ""


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
            items.append(dict(source=source, title=title, link=link, summary=summary, image=find_image(e), when=when.astimezone(TZ)))
    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:MAX_ITEMS]


# Watch section. Value is an @handle (resolved at build time) or a UC... channel ID.
# To add a language later, add another key, e.g. "Hindi": {...}.
CHANNELS = {
    "English": {
        "Matt Wolfe": "@mreflow",
        "Matthew Berman": "UCawZsQWqfGSbCI5yjkdVkTA",
        "Two Minute Papers": "@TwoMinutePapers",
        "Fireship": "@Fireship",
        "Lex Fridman": "@lexfridman",
        "3Blue1Brown": "@3blue1brown",
    },
}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def channel_id(ref):
    if ref.startswith("UC"):
        return ref
    req = urllib.request.Request(f"https://www.youtube.com/{ref}",
                                 headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Cookie": "SOCS=CAI"})
    try:
        page = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception as exc:
        print(f"could not load {ref}: {exc}", file=sys.stderr)
        return None
    for pat in (r'rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
                r"feeds/videos\.xml\?channel_id=(UC[\w-]{22})",
                r'"externalId":"(UC[\w-]{22})"'):
        m = re.search(pat, page)
        if m:
            return m.group(1)
    return None


def fetch_videos(per_channel=2):
    vids = []
    for lang, chans in CHANNELS.items():
        for name, ref in chans.items():
            cid = channel_id(ref)
            if not cid:
                print(f"could not resolve {name} ({ref})", file=sys.stderr)
                continue
            feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", agent="ai-news-digest/1.0")
            n = 0
            for e in feed.entries:
                vid, ts = e.get("yt_videoid", ""), e.get("published_parsed")
                if not re.fullmatch(r"[\w-]{11}", vid) or not ts:
                    continue
                when = datetime(*ts[:6], tzinfo=timezone.utc).astimezone(TZ)
                vids.append(dict(id=vid, title=clean(e.get("title")), channel=name, lang=lang, when=when))
                n += 1
                if n >= per_channel:
                    break
            if not n:
                print(f"no videos from {name}", file=sys.stderr)
    vids.sort(key=lambda v: v["when"], reverse=True)
    return vids


def watch_html(videos, limit=8):
    langs = list(dict.fromkeys(v["lang"] for v in videos))
    out = []
    for lang in langs:
        group = [v for v in videos if v["lang"] == lang][:limit]
        title = "Watch" if len(langs) == 1 else f"Watch: {lang}"
        tiles = "".join(
            f'<a class="vid" href="https://www.youtube.com/watch?v={v["id"]}" data-id="{v["id"]}" rel="noopener">'
            f'<span class="media"><img src="https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg" alt="" loading="lazy" decoding="async" '
            f'referrerpolicy="no-referrer"><span class="play" aria-hidden="true"></span></span>'
            f'<span class="txt"><span class="meta"><span class="src">{html.escape(v["channel"])}</span>'
            f'<time datetime="{v["when"].isoformat()}">{v["when"].strftime("%b %-d")}</time></span>'
            f'<span class="t">{html.escape(v["title"])}</span></span></a>' for v in group)
        out.append(f'<section class="watch"><h2>{title}</h2><div class="vgrid">{tiles}</div></section>')
    return "".join(out)


def img_tag(it):
    if not it["image"]:
        return ""
    return (f'<img src="{html.escape(it["image"])}" alt="" loading="lazy" decoding="async" '
            f'referrerpolicy="no-referrer" onerror="this.remove()">')


def meta(it):
    return (f'<div class="meta"><span class="src">{html.escape(it["source"])}</span>'
            f'<time datetime="{it["when"].isoformat()}">{it["when"].strftime("%-I:%M %p")}</time></div>')


def card(it, cls):
    esc = html.escape
    summ = f'<p>{esc(it["summary"])}</p>' if it["summary"] else ""
    return (f'<article class="{cls}"><a class="media" href="{esc(it["link"])}" rel="noopener" tabindex="-1" aria-hidden="true">{img_tag(it)}</a>'
            f'<div class="txt">{meta(it)}<a class="t" href="{esc(it["link"])}" rel="noopener">{esc(it["title"])}</a>{summ}</div></article>')


def day_label(d, today):
    return "Today" if d == today else "Yesterday" if d == today - timedelta(days=1) else d.strftime("%A, %B %-d")


def render(items, videos=()):
    esc = html.escape
    today = datetime.now(TZ).date()
    with_img = [i for i in items if i["image"]]
    hero = with_img[0] if with_img else None
    grid = with_img[1:10]
    used = {id(i) for i in ([hero] if hero else []) + grid}
    rest = [i for i in items if id(i) not in used]

    body = []
    if hero:
        body.append(card(hero, "hero"))
    if grid:
        body.append('<div class="grid">' + "".join(card(i, "tile") for i in grid) + "</div>")
    if videos:
        body.append(watch_html(videos))
    day = None
    for it in rest:
        d = it["when"].date()
        if d != day:
            if day:
                body.append("</ol></section>")
            day = d
            body.append(f'<section><h2>{day_label(d, today)}</h2><ol>')
        body.append(f'<li>{meta(it)}<div><a class="t" href="{esc(it["link"])}" rel="noopener">{esc(it["title"])}</a>'
                    + (f'<p>{esc(it["summary"])}</p>' if it["summary"] else "") + "</div></li>")
    if day:
        body.append("</ol></section>")
    if not items:
        body.append("<p class='empty'>No stories could be loaded. The next scheduled update will try again.</p>")
    stamp = datetime.now(TZ).strftime("%B %-d, %-I:%M %p %Z")
    return PAGE.replace("{{STAMP}}", stamp).replace("{{COUNT}}", str(len(items))).replace("{{BODY}}", "\n".join(body))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>AI News</title>
<meta name="description" content="AI headlines from leading sources, updated twice a day.">
<style>
:root{--bg:#f3f5f8;--card:#fff;--ink:#141a24;--mute:#5a6578;--line:#d5dbe5;--link:#1f3fd6;--ph:#dfe4ec;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--bg:#10141c;--card:#171d29;--ink:#e8ecf3;--mute:#93a0b6;--line:#2a3344;--link:#8da2ff;--ph:#232b3a;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
main{max-width:1040px;margin:0 auto;padding:48px 20px 80px}
header{border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:28px}
h1{font:700 clamp(40px,9vw,72px)/1 "Iowan Old Style",Palatino,Georgia,serif;letter-spacing:-.02em;margin:0 0 12px}
.status{margin:0;color:var(--mute);font-size:14px}
.meta{display:flex;gap:10px;font-size:13px;color:var(--mute)}
.src{font-weight:600;color:var(--ink)}
.t{font:600 19px/1.3 "Iowan Old Style",Palatino,Georgia,serif;color:var(--ink);text-decoration:none}
.t:hover{color:var(--link);text-decoration:underline}
.t:focus-visible{outline:2px solid var(--link);outline-offset:3px}
p{margin:6px 0 0;color:var(--mute);font-size:15px;max-width:62ch}
.media{display:block;aspect-ratio:16/9;background:var(--ph);overflow:hidden;border-radius:6px}
.media img{width:100%;height:100%;object-fit:cover;display:block}
.txt{display:flex;flex-direction:column;gap:6px;padding-top:12px}
.hero{display:grid;grid-template-columns:1.4fr 1fr;gap:28px;align-items:center;margin-bottom:36px}
.hero .txt{padding:0}
.hero .t{font-size:clamp(26px,3.6vw,38px);line-height:1.15}
.hero p{font-size:17px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:28px 22px;margin-bottom:12px}
.tile .txt p{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.vid{display:block;color:inherit;text-decoration:none}
.vid .t{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:16px}
.vid:hover .t{color:var(--link);text-decoration:underline}
.vid:focus-visible{outline:2px solid var(--link);outline-offset:4px;border-radius:6px}
.media{position:relative}
.media iframe{width:100%;height:100%;border:0;display:block}
.play{position:absolute;left:50%;top:50%;width:52px;height:52px;margin:-26px 0 0 -26px;border-radius:50%;background:rgba(0,0,0,.65)}
.play::after{content:"";position:absolute;left:21px;top:16px;border-left:16px solid #fff;border-top:10px solid transparent;border-bottom:10px solid transparent}
.watch{max-width:none;margin-top:8px}
.vgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:14px}
h2{font:600 15px/1 system-ui,sans-serif;color:var(--mute);margin:40px 0 4px}
ol{list-style:none;margin:0;padding:0}
li{display:grid;grid-template-columns:170px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid var(--line)}
li .meta{flex-direction:column;gap:0}
section{max-width:780px}
.empty{margin-top:32px}
@media(max-width:820px){.hero{grid-template-columns:1fr}.grid,.vgrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.grid,.vgrid{grid-template-columns:1fr}li{grid-template-columns:1fr;gap:4px}li .meta{flex-direction:row;gap:10px}}
</style></head><body><main>
<header><h1>AI News</h1>
<p class="status">Updated {{STAMP}}. {{COUNT}} stories from the last few days. Refreshes twice a day.</p></header>
{{BODY}}
<script>
document.addEventListener("click",function(e){var a=e.target.closest("a.vid");if(!a)return;e.preventDefault();
var m=a.querySelector(".media");m.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/'+a.dataset.id+'?autoplay=1" title="Video player" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>';
a.classList.remove("vid");a.removeAttribute("href");});
</script>
</main></body></html>
"""

if __name__ == "__main__":
    out = Path(__file__).parent / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(render(fetch(), fetch_videos()), encoding="utf-8")
    print("wrote", out / "index.html")
