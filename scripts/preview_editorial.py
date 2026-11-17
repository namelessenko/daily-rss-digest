"""Offline layout demonstration; all story text is explicitly fictional."""
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from digest.core import load_config, render_site, stamp

root = Path(__file__).resolve().parents[1]
cfg = load_config(root / "config.toml")
cfg.update(site_url="https://example.org/digest", title="Your daily briefing · layout preview",
           description="Ukraine · Europe & world politics · New science")
stories = [
    {"headline": "Example: a development with concrete military consequences", "rating": 5,
     "category": "ukraine", "rating_reason": "Example explanation of the potential effect on capacity or civilian protection, with uncertainty stated.",
     "summary": "Layout demonstration only — this is not a news report. A real digest would summarize feed evidence, attribute contested claims and explain the practical consequences.", "article_ids": ["1"]},
    {"headline": "Example: a consequential European policy decision", "rating": 4,
     "category": "europe", "rating_reason": "Example explanation of what the decision changes, who is affected and when.",
     "summary": "The rating sits beside the topic, followed by a short summary, an explanation of importance and the original source.", "article_ids": ["2"]},
    {"headline": "Example: a new study with clearly stated limitations", "rating": 3,
     "category": "science", "rating_reason": "An informative finding, with study design and limitations made explicit.",
     "summary": "Science coverage distinguishes preliminary findings from established evidence. Stories without a feed-provided image retain the same readable layout.", "article_ids": ["3"]},
]
sources = {str(i): {"title": "Illustrative source link", "source": "Demo source",
                   "url": "https://example.org/article",
                   "image": "https://example.org/layout-photo.svg" if i == 1 else ""}
           for i in range(1, 4)}
state = {"history": [{"date": "2026-11-18", "created": stamp(datetime(2026, 11, 18, 16, tzinfo=timezone.utc)),
                     "summary": {"intro": "A preview of the new layout. All examples below are fictional.", "stories": stories},
                     "sources": sources}]}
out = root / "editorial-preview"
render_site(state, cfg, out)
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 480"><rect width="1000" height="480" fill="#dce8ed"/><path d="M0 400L260 130L480 330L700 170L1000 410V480H0Z" fill="#7a969b"/><circle cx="800" cy="95" r="40" fill="#e6ba62"/><rect y="400" width="1000" height="80" fill="#172438"/><text x="45" y="450" fill="white" font-size="28" font-family="sans-serif">Article image placement · illustrative placeholder</text></svg>'
(out / "layout-photo.svg").write_text(svg)
page = (out / "index.html").read_text().replace("https://example.org/layout-photo.svg", "layout-photo.svg")
(out / "index.html").write_text(page)
