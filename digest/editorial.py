"""Editorial policy, feed-provided photos, and RSS-compatible story cards."""
import html
import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

CATEGORIES = ("ukraine", "europe", "world", "science", "other")
LABELS = {"ukraine": "Ukraine · war impact", "europe": "European politics",
          "world": "World politics", "science": "Science · new research", "other": "Other"}
POLICY = """
Reader priorities, in order:
1. The ongoing war in Ukraine: developments with concrete effects on military capacity,
front lines, civilian protection, infrastructure, logistics, arms deliveries, funding,
sanctions enforcement, or negotiations. Routine rhetoric, recycled claims, isolated
incidents with no demonstrated wider effect, and unsupported casualty claims are noise.
Attribute contested claims. Do not infer a strategic breakthrough from one report.
2. European politics, then world politics: enacted decisions and consequential changes.
3. New scientific studies: explain what was studied, the finding and its limits.
Distinguish preprints, peer-reviewed studies, animal studies and human studies when known.
Do not infer causation from an association or turn preliminary findings into medical advice.
Assign each grouped story a category: ukraine, europe, world, science, or other.
Assign an integer rating 1–5 for importance TO THIS READER, not truth or certainty:
5 = exceptional, demonstrated major impact; 4 = substantial concrete development;
3 = useful relevant update; 2 = marginal, repetitive or speculative; 1 = irrelevant/noise.
For other topics, use 1 or 2. Importance does not increase because a title is sensational.
Give one short rating_reason explaining the concrete impact and any uncertainty.
Keep the headline free of ratings and decoration; the renderer formats them.
All input IDs must still occur exactly once, including low-rated stories. Stories below
3 will be hidden by the renderer: keep their summaries brief. The intro should discuss
only stories rated 3–5. If none qualify, say there are no substantial relevant updates.
"""

# A transparent shortlist heuristic, not an importance or credibility assessment.
# Gemini assigns the final category/rating from the supplied excerpts.
PATTERNS = [
    r"ukrain|україн|украин|kyiv|kiev|київ|киев|zelensky|зеленськ|зеленск|donbas|донбас|kherson|херсон|зсу|afu\b",
    r"\beu\b|europe|european|bundestag|brussels|german|france|french|poland|polish|britain|election|parliament|sanction|nato|європ|европ|німеч|герман|польщ|польш",
    r"politic|president|government|diplomac|treaty|ceasefire|політик|политик|уряд|правительств",
    r"study|studies|research|scient|trial|journal|preprint|discovery|дослідж|исследован|наук",
]

def shortlist(queue, limit):
    buckets = [[] for _ in range(5)]
    for article in queue:
        text = (article["title"] + " " + article["excerpt"]).lower()
        category = next((i for i, pattern in enumerate(PATTERNS)
                         if re.search(pattern, text)), 4)
        buckets[category].append(article)
    # Reserve roughly 50% Ukraine, 30% politics, 20% science; fill unused slots.
    order = [0, 0, 1, 0, 2, 0, 1, 3, 0, 3]
    selected = []
    while len(selected) < limit and any(buckets):
        for category in (order if any(buckets[:4]) else [4]):
            if buckets[category] and len(selected) < limit:
                selected.append(buckets[category].pop(0))
    return selected

def image_url(value, base=""):
    try:
        url = urljoin(base, str(value or "").strip())
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return ""
        if any(c.isspace() for c in url) or len(url) > 3000:
            return ""
        if p.hostname.lower() == "localhost" or p.hostname.lower().endswith((".localhost", ".local", ".internal")):
            return ""
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                return ""
        except ValueError:
            pass
        return url
    except ValueError:
        return ""

class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attrs = dict(attrs)
        if any(str(attrs.get(k, "")).isdigit() and int(attrs[k]) <= 2 for k in ("width", "height")):
            return
        self.urls.append(attrs.get("src") or attrs.get("data-src"))

def article_image(entry, body, base):
    candidates = []
    for obj in entry.get("media_content", []):
        if (obj.get("medium") == "image" or obj.get("type", "").startswith("image/")
                or re.search(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", obj.get("url", ""), re.I)):
            candidates.append(obj.get("url"))
    candidates += [o.get("url") for o in entry.get("media_thumbnail", [])]
    candidates += [o.get("href") for o in entry.get("enclosures", []) if o.get("type", "").startswith("image/")]
    parser = Images()
    parser.feed(body or "")
    candidates += parser.urls
    return next((url for candidate in candidates if (url := image_url(candidate, base))), "")

def metadata(story, error):
    fields = ("rating", "category", "rating_reason")
    if not any(k in story for k in fields):
        return {}  # Existing saved digests remain readable, without invented ratings.
    rating = story.get("rating")
    if type(rating) is not int or not 1 <= rating <= 5 or story.get("category") not in CATEGORIES:
        raise error("Invalid story rating or category")
    reason = story.get("rating_reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 600:
        raise error("Invalid rating explanation")
    return {k: story[k] for k in fields}

def story_key(story):
    return (CATEGORIES.index(story.get("category", "other")), -story.get("rating", 0))

def card(story, sources, http_url):
    e = html.escape
    parts = ['<div style="margin:22px 0;padding:20px;border:1px solid #dce2e8;border-radius:12px;background:#fff;color:#172438">']
    if "rating" in story:
        rating = story["rating"]
        stars = "★" * rating + "☆" * (5 - rating)
        parts.append(f'<p style="margin:0 0 8px;color:#176050;font-size:14px"><strong>{e(LABELS[story["category"]])}</strong> · {stars} {rating}/5 impact</p>')
    parts.append(f'<h3 style="font-size:22px;line-height:1.3;margin:8px 0 16px">{e(story["headline"])}</h3>')
    for ref in story["article_ids"]:
        source = sources[ref]
        photo = image_url(source.get("image", ""))
        if photo:
            link = e(http_url(source["url"]), quote=True)
            parts.append(f'<p><a href="{link}"><img src="{e(photo, quote=True)}" alt="{e(source["title"], quote=True)}" width="680" loading="lazy" referrerpolicy="no-referrer" style="display:block;width:100%;max-width:680px;height:auto;border-radius:8px"></a><small>Image from the feed of {e(source["source"])}; see the original article for context and credits.</small></p>')
            break
    parts.append(f'<p>{e(story["summary"])}</p>')
    if "rating_reason" in story:
        parts.append(f'<p style="border-left:3px solid #176050;padding-left:12px"><strong>Why it matters:</strong> {e(story["rating_reason"])}</p>')
    parts.append('<ul>')
    for ref in story["article_ids"]:
        source = sources[ref]
        parts.append(f'<li><a href="{e(http_url(source["url"]), quote=True)}">{e(source["title"])}</a> — {e(source["source"])}</li>')
    parts.append('</ul></div>')
    return "\n".join(parts)
