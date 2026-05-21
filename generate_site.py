from __future__ import annotations

import email.utils
import html
import json
import os
import re
import smtplib
import sys
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "energy-news-config.json"
OUTPUT_DIR = ROOT / "public"
OUTPUT_PATH = OUTPUT_DIR / "index.html"


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: datetime
    key: str


def text_from_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def child_link(node: ET.Element) -> str:
    link = child_text(node, {"link"})
    if link:
        return link
    for child in list(node):
        if local_name(child.tag) == "link" and child.attrib.get("href"):
            return child.attrib["href"]
    return ""


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def fetch_feed(feed: dict) -> list[NewsItem]:
    request = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": "IndiaEnergyNewsDigest/1.0 (+https://github.com/)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()
    root = ET.fromstring(content)
    nodes = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[NewsItem] = []
    for node in nodes:
        title = text_from_html(child_text(node, {"title"}))
        summary = text_from_html(child_text(node, {"description", "summary", "content", "encoded"}))
        link = child_link(node).strip()
        published_raw = child_text(node, {"pubdate", "published", "updated", "date"})
        published = parse_date(published_raw)
        if not title:
            continue
        key = (link or f"{feed['name']}|{title}").lower()
        items.append(NewsItem(feed["name"], title, summary, link, published, key))
    return items


def matches(item: NewsItem, config: dict) -> bool:
    haystack = f"{item.title} {item.summary}".lower()
    for word in config.get("excludeKeywords", []):
        if word and word.lower() in haystack:
            return False
    keywords = [word.lower() for word in config.get("keywords", []) if word]
    return any(word in haystack for word in keywords)


def collect_items(config: dict) -> list[NewsItem]:
    since = datetime.now(timezone.utc) - timedelta(hours=float(config.get("lookbackHours", 24)))
    seen: set[str] = set()
    items: list[NewsItem] = []
    for feed in config["feeds"]:
        try:
            for item in fetch_feed(feed):
                if item.published >= since and matches(item, config) and item.key not in seen:
                    seen.add(item.key)
                    items.append(item)
        except Exception as exc:
            print(f"WARNING: feed failed: {feed['name']} - {exc}", file=sys.stderr)
    items.sort(key=lambda item: item.published, reverse=True)
    return items[: int(config.get("maxItems", 40))]


def category_for(item: NewsItem) -> str:
    text = f"{item.source} {item.title} {item.summary}".lower()
    if any(x in text for x in ["solar", "wind", "renewable", "battery", "storage", "green hydrogen"]):
        return "Renewables & Storage"
    if any(x in text for x in ["oil", "gas", "lng", "petroleum", "refinery", "cng", "png"]):
        return "Oil & Gas"
    if "coal" in text:
        return "Coal"
    if any(x in text for x in ["mnre", "ministry", "cerc", "cea", "seci", "policy", "tariff"]):
        return "Policy"
    return "Power & Grid"


def render_site(config: dict, items: list[NewsItem]) -> str:
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    generated_date = now_ist.strftime("%Y-%m-%d")
    cards = []
    for item in items:
        published_ist = item.published.astimezone(timezone(timedelta(hours=5, minutes=30)))
        category = category_for(item)
        cards.append(
            f"""
            <article class="item" data-source="{html.escape(item.source)}" data-category="{html.escape(category)}">
              <div class="meta">
                <span>{html.escape(category)}</span>
                <span>{html.escape(item.source)}</span>
                <time>{published_ist.strftime('%d %b %Y, %H:%M IST')}</time>
              </div>
              <h2><a href="{html.escape(item.link)}" target="_blank" rel="noopener noreferrer">{html.escape(item.title)}</a></h2>
              <p>{html.escape(item.summary or 'No summary available.')}</p>
            </article>
            """
        )
    if not cards:
        cards.append('<article class="item"><h2>No fresh India energy news found</h2><p>The next scheduled refresh will try again.</p></article>')

    sources = sorted({item.source for item in items})
    source_options = "\n".join(f'<option value="{html.escape(source)}">{html.escape(source)}</option>' for source in sources)
    categories = ["Power & Grid", "Renewables & Storage", "Oil & Gas", "Coal", "Policy"]
    category_options = "\n".join(f'<option value="{html.escape(cat)}">{html.escape(cat)}</option>' for cat in categories)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>{html.escape(config['siteTitle'])}</title>
  <style>
    :root {{ --ink:#17242c; --muted:#60717c; --line:#d9e1e5; --bg:#f6f8f9; --panel:#fff; --teal:#087f8c; --coral:#c94f3d; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:"Segoe UI",Arial,sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:28px clamp(16px,4vw,42px); }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); letter-spacing:0; }}
    .lede {{ max-width:860px; margin:0; color:var(--muted); line-height:1.55; }}
    main {{ padding:20px clamp(16px,4vw,42px) 42px; }}
    .toolbar {{ display:grid; grid-template-columns: minmax(180px,1fr) minmax(180px,1fr) minmax(220px,1.4fr); gap:12px; margin-bottom:16px; }}
    label {{ display:grid; gap:6px; color:var(--muted); font-size:12px; font-weight:700; }}
    select,input {{ height:40px; border:1px solid var(--line); border-radius:6px; padding:0 10px; font:inherit; background:#fff; color:var(--ink); }}
    .stats {{ display:grid; grid-template-columns:repeat(3,minmax(160px,1fr)); gap:12px; margin-bottom:16px; }}
    .stat,.item {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .stat {{ padding:14px; }}
    .stat b {{ display:block; font-size:28px; margin-top:6px; }}
    .feed {{ display:grid; gap:12px; }}
    .item {{ padding:16px; }}
    .meta {{ display:flex; gap:8px; flex-wrap:wrap; color:var(--muted); font-size:12px; font-weight:700; }}
    .meta span:first-child {{ color:#fff; background:var(--teal); border-radius:999px; padding:3px 8px; }}
    h2 {{ margin:10px 0 8px; font-size:20px; line-height:1.3; letter-spacing:0; }}
    a {{ color:#075e69; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    p {{ line-height:1.55; }}
    .item p {{ margin-bottom:0; color:#344650; }}
    footer {{ padding:18px clamp(16px,4vw,42px) 32px; color:var(--muted); font-size:12px; }}
    @media (max-width:760px) {{ .toolbar,.stats {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(config['siteTitle'])}</h1>
    <p class="lede">{html.escape(config['siteDescription'])}</p>
  </header>
  <main>
    <section class="toolbar" aria-label="Filters">
      <label>Category<select id="category"><option value="">All categories</option>{category_options}</select></label>
      <label>Source<select id="source"><option value="">All sources</option>{source_options}</select></label>
      <label>Search<input id="search" type="search" placeholder="Search title or summary"></label>
    </section>
    <section class="stats" data-generated-date="{generated_date}">
      <div class="stat">Stories<b id="count">{len(items)}</b></div>
      <div class="stat">Sources<b>{len(sources)}</b></div>
      <div class="stat">Updated<b>{now_ist.strftime('%d %b, %H:%M')}</b></div>
    </section>
    <section class="feed" id="feed">
      {''.join(cards)}
    </section>
  </main>
  <footer>
    Refreshed automatically by GitHub Actions. Times shown in IST. Stories link to the original publishers.
  </footer>
  <script>
    const category = document.getElementById('category');
    const source = document.getElementById('source');
    const search = document.getElementById('search');
    const count = document.getElementById('count');
    const items = [...document.querySelectorAll('.item')];
    const stats = document.querySelector('.stats');
    const generatedDate = stats?.dataset.generatedDate;
    const today = new Date().toLocaleDateString('en-CA', {{ timeZone: 'Asia/Kolkata' }});
    const refreshedKey = 'indiaEnergyDigestRefreshDate';
    if (generatedDate && generatedDate < today && sessionStorage.getItem(refreshedKey) !== today) {{
      sessionStorage.setItem(refreshedKey, today);
      const url = new URL(window.location.href);
      url.searchParams.set('refresh', Date.now().toString());
      window.location.replace(url.toString());
    }}
    function applyFilters() {{
      const c = category.value;
      const s = source.value;
      const q = search.value.trim().toLowerCase();
      let visible = 0;
      items.forEach(item => {{
        const ok = (!c || item.dataset.category === c) && (!s || item.dataset.source === s) && (!q || item.textContent.toLowerCase().includes(q));
        item.style.display = ok ? '' : 'none';
        if (ok) visible++;
      }});
      count.textContent = visible;
    }}
    [category, source, search].forEach(el => el.addEventListener('input', applyFilters));
  </script>
</body>
</html>"""


def send_email(config: dict, html_body: str, item_count: int) -> None:
    server = os.getenv("SMTP_SERVER")
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or username
    port = int(os.getenv("SMTP_PORT", "587"))
    recipients = [x for x in config.get("recipients", []) if x and "@" in x and not x.startswith("recipient@")]
    if not (server and username and password and sender and recipients):
        print("Email not sent: SMTP secrets or recipients are not configured.")
        return
    message = EmailMessage()
    message["Subject"] = f"{config['subjectPrefix']} - {datetime.now().strftime('%Y-%m-%d')} - {item_count} stories"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content("Your email client does not support HTML. Please open the public digest link.")
    message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
    print(f"Email sent to {len(recipients)} recipient(s).")


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    items = collect_items(config)
    html_body = render_site(config, items)
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(html_body, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(items)} stories.")
    if os.getenv("SEND_EMAIL", "").lower() == "true":
        send_email(config, html_body, len(items))


if __name__ == "__main__":
    main()
