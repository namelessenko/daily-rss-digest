import copy
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from digest import core as d, editorial as e
from test_digest import NOW, summary


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.cfg = d.load_config(Path("config.toml"))
        self.cfg["site_url"] = "https://example.org/digest"
        self.items = d.parse_feed(Path("tests/fixtures/sample.rss").read_bytes(),
                                 {"url": "https://example.org/rss", "title": "Source"},
                                 "https://example.org/rss", self.cfg, NOW)

    def test_images_from_media_enclosure_html_and_unsafe_urls(self):
        for entry, body, expected in [
            ({"media_content": [{"url": "https://cdn.example.org/p.jpg"}]}, "", "https://cdn.example.org/p.jpg"),
            ({"media_thumbnail": [{"url": "/photo.jpg"}]}, "", "https://example.org/photo.jpg"),
            ({"enclosures": [{"href": "https://cdn.example.org/a", "type": "image/jpeg"}]}, "", "https://cdn.example.org/a"),
            ({}, '<img width="1" height="1" src="/pixel"><img src="/photo.jpg">', "https://example.org/photo.jpg"),
            ({}, '<img src="javascript:alert(1)"><img src="http://localhost/a">', ""),
        ]:
            with self.subTest(entry=entry, body=body):
                self.assertEqual(e.article_image(entry, body, "https://example.org/news"), expected)
        for url in ["https://127.0.0.1/p.jpg", "https://[::1]/p", "https://user:pass@example.org/p", "data:image/png,a"]:
            self.assertEqual(e.image_url(url), "")

    def test_story_order_uses_rating_and_neutral_label(self):
        stories = [{"category": "ukraine", "rating": 3}, {"category": "science", "rating": 5},
                   {"category": "world", "rating": 4}]
        self.assertEqual([s["category"] for s in sorted(stories, key=e.story_key)],
                         ["science", "world", "ukraine"])
        self.assertEqual(e.LABELS["ukraine"], "Ukraine")
        self.assertIn("economy", d.schema_for(["1"])["properties"]["stories"]["items"]["properties"]["category"]["enum"])
        self.assertEqual(e.metadata({"category": "economy", "rating": 4, "rating_reason": "Changes household costs."}, d.DigestError)["category"], "economy")
        tied = [{"category": "science", "rating": 4}, {"category": "ukraine", "rating": 4}]
        self.assertEqual(sorted(tied, key=e.story_key), tied)

    def test_ratings_validation_and_legacy_history(self):
        result = summary(self.items)
        for rating in [0, 6, True, "5"]:
            bad = copy.deepcopy(result)
            bad["stories"][0]["rating"] = rating
            with self.assertRaises(d.DigestError):
                d.validate_summary(bad, ["1", "2"])
        for story in result["stories"]:
            for field in ["rating", "category", "rating_reason"]:
                del story[field]
        d.validate_summary(result, ["1", "2"])
        with self.assertRaises(d.DigestError):
            d.validate_summary(result, ["1", "2"], require_ratings=True)

    def test_shortlist_reserves_science_and_ukraine_and_keeps_unselected(self):
        items = []
        for i, title in enumerate(["Celebrity gossip"] * 20 + ["Ukraine air defence deliveries"] * 12 +
                                  ["European parliament vote"] * 8 + ["New scientific study"] * 8 + ["European inflation report"] * 8):
            a = copy.deepcopy(self.items[0])
            a.update(title=title, excerpt="", keys=[d.fingerprint(str(i))],
                     url=f"https://example.org/{i}")
            items.append(a)
        self.cfg["max_articles"] = 20
        state, _ = d.advance(d.empty_state(), items, self.cfg, NOW, summary)
        titles = [a["title"] for a in state["history"][0]["sources"].values()]
        self.assertIn("New scientific study", titles)
        self.assertIn("Ukraine air defence deliveries", titles)
        counts = [titles.count(title) for title in ("Ukraine air defence deliveries", "European parliament vote", "New scientific study", "European inflation report")]
        self.assertLessEqual(max(counts) - min(counts), 1)
        seen = set(state["seen"])
        pending = {k for a in state["pending"] for k in a["keys"]}
        self.assertFalse(seen & pending)
        self.assertEqual(len(seen | pending), len(items))

    def test_rss_contains_image_rating_escaped_text_and_filters_noise(self):
        self.items[0]["image"] = "https://cdn.example.org/photo.jpg?a=1&b=2"
        def rated(items):
            result = summary(items)
            for story, article in zip(result["stories"], items):
                story.update(rating=5 if article.get("image") else 1,
                             category="ukraine" if article.get("image") else "other",
                             rating_reason='<script>alert("bad")</script>')
            return result
        state, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, rated)
        with tempfile.TemporaryDirectory() as tmp:
            d.render_site(state, self.cfg, Path(tmp))
            body = ET.parse(Path(tmp) / "feed.xml").findtext("channel/item/description")
            self.assertIn("★★★★★ 5/5", body)
            self.assertIn('<img src="https://cdn.example.org/photo.jpg?a=1&amp;b=2"', body)
            self.assertIn("1 low-priority stories omitted", body)
            self.assertNotIn("<script>", body)
            d.save_state(Path(tmp) / "state.json", state)
            self.assertEqual(d.load_state(Path(tmp) / "state.json"), state)

    def test_rss_and_atom_image_parsing(self):
        xml = b'<rss version="2.0"><channel><title>X</title><item><title>Story</title><link>https://example.org/a</link><pubDate>Thu, 05 Nov 2026 05:00:00 GMT</pubDate><enclosure url="https://cdn.example.org/a.jpg" type="image/jpeg" length="123"/></item></channel></rss>'
        article = d.parse_feed(xml, {"title": "Source", "url": "https://example.org/rss"},
                               "https://example.org/rss", self.cfg, NOW)[0]
        self.assertEqual(article["image"], "https://cdn.example.org/a.jpg")
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>X</title><entry><title>X</title><link href="https://example.org/a"/><updated>2026-11-05T05:00:00Z</updated><content type="html">&lt;img src="/p.jpg"&gt;</content></entry></feed>'
        article = d.parse_feed(atom, {"title": "Source", "url": "https://example.org/rss"},
                               "https://example.org/rss", self.cfg, NOW)[0]
        self.assertEqual(article["image"], "https://example.org/p.jpg")
