import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import feedparser
import requests
import yaml

from digest import core as d

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 5, 6, 17, tzinfo=d.UTC)
SOURCE = {"url": "https://example.org/feed", "title": "Example"}


def summary(items):
    return {"title": "Daily news", "intro": "What happened today.", "stories": [
        {"headline": a["title"], "summary": a["excerpt"] or "No excerpt.", "article_ids": [str(i)]}
        for i, a in enumerate(items, 1)]}


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"SITE_URL": "", "GEMINI_MODEL": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cfg = d.load_config(ROOT / "config.toml")
        self.cfg["site_url"] = "https://reader.github.io/daily"
        self.rss = (ROOT / "tests/fixtures/sample.rss").read_bytes()
        self.items = d.parse_feed(self.rss, SOURCE, SOURCE["url"], self.cfg, NOW)

    def test_nested_opml_and_duplicate_subscriptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "feeds.opml"
            file.write_text('<opml><body><outline text="Folder"><outline xmlUrl="https://example.org/rss"/><outline xmlUrl="https://example.org/rss"/></outline></body></opml>')
            self.assertEqual(len(d.read_opml(file, 10)), 1)
            with self.assertRaises(d.DigestError):
                d.read_opml(file, 0)

    def test_opml_rejects_entities_and_empty_feeds(self):
        for body in ['<!DOCTYPE opml [<!ENTITY x SYSTEM "file:///etc/passwd">]><opml>&x;</opml>', '<opml><body/></opml>']:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                file = Path(tmp) / "feeds.opml"
                file.write_text(body)
                with self.assertRaises(d.DigestError):
                    d.read_opml(file, 10)

    def test_rss_and_atom_parsing(self):
        self.assertEqual(len(self.items), 2)
        self.assertEqual(self.items[0]["url"], "https://example.org/library")
        self.assertNotIn("ignore me", self.items[0]["excerpt"])
        atom = d.parse_feed((ROOT / "tests/fixtures/sample.atom").read_bytes(), SOURCE, SOURCE["url"], self.cfg, NOW)
        self.assertEqual(len(atom), 1)
        self.assertEqual(atom[0]["excerpt"], "An Atom update.")
        self.assertEqual(atom[0]["published"], "2026-11-04T10:00:00+00:00")

    def test_old_and_future_articles_excluded_undated_included(self):
        data = self.rss.replace(b"2026 12:00:00", b"2020 12:00:00").replace(b"2026 04:00:00", b"2030 04:00:00")
        self.assertEqual(d.parse_feed(data, SOURCE, SOURCE["url"], self.cfg, NOW), [])
        data = self.rss.replace(b"<pubDate>Wed, 04 Nov 2026 12:00:00 GMT</pubDate>", b"")
        self.assertIsNone(d.parse_feed(data, SOURCE, SOURCE["url"], self.cfg, NOW)[0]["published"])

    def test_rejects_non_feed_and_unsafe_links(self):
        with self.assertRaises(d.DigestError):
            d.parse_feed(b"<html><body>Not a feed</body></html>", SOURCE, SOURCE["url"], self.cfg, NOW)
        data = self.rss.replace(b"https://example.org/cycling", b"javascript:alert(1)")
        self.assertEqual(len(d.parse_feed(data, SOURCE, SOURCE["url"], self.cfg, NOW)), 1)

    def test_tracking_dedup_preserves_semantic_query(self):
        self.assertEqual(d.canonical_url("https://EXAMPLE.org/a?id=1&utm_source=x&fbclid=z#frag"), "https://example.org/a?id=1")
        self.assertNotEqual(d.canonical_url("https://example.org/a?id=1"), d.canonical_url("https://example.org/a?id=2"))
        for bad in ["javascript:alert(1)", "file:///a", "https://user:pass@example.org/a"]:
            with self.assertRaises(d.DigestError):
                d.http_url(bad)

    def test_public_address_check(self):
        with patch.object(d.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with self.assertRaises(d.DigestError):
                d.public_url("http://localhost/rss")

    def test_global_url_and_feed_local_guid_dedup(self):
        duplicate = copy.deepcopy(self.items[0])
        duplicate["keys"].append(d.fingerprint("another feed guid"))
        queue, seen = d.merge_queue(self.items, [duplicate], [])
        self.assertEqual(len(queue), 2)
        self.assertIn(duplicate["keys"][-1], queue[0]["keys"])
        queue, seen = d.merge_queue([], [duplicate], [self.items[0]["keys"][0]])
        self.assertEqual(queue, [])
        self.assertIn(duplicate["keys"][-1], seen)

    def test_transitive_deduplication(self):
        a, b, bridge = [copy.deepcopy(self.items[0]) for _ in range(3)]
        a["keys"], b["keys"], bridge["keys"] = ["a", "b"], ["c", "d"], ["b", "c"]
        queue, _ = d.merge_queue([a, b], [bridge], [])
        self.assertEqual(len(queue), 1)
        self.assertEqual(set(queue[0]["keys"]), {"a", "b", "c", "d"})

    def test_overflow_is_queued_and_next_day_processed(self):
        self.cfg["max_articles"] = 1
        first, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
        self.assertEqual(len(first["pending"]), 1)
        second, _ = d.advance(first, self.items, self.cfg, NOW + timedelta(days=1), summary)
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["pending"], [])

    def test_same_day_rerun_never_calls_gemini(self):
        self.cfg["max_articles"] = 1
        first, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
        forbidden = MagicMock(side_effect=AssertionError("Must not call Gemini"))
        rerun, _ = d.advance(first, self.items, self.cfg, NOW, forbidden)
        self.assertEqual(len(rerun["history"]), 1)
        self.assertEqual(len(rerun["pending"]), 1)
        forbidden.assert_not_called()

    def test_empty_day_no_request_or_digest(self):
        forbidden = MagicMock(side_effect=AssertionError())
        state, _ = d.advance(d.empty_state(), [], self.cfg, NOW, forbidden)
        self.assertEqual(state["history"], [])
        forbidden.assert_not_called()

    def test_failed_generation_does_not_mutate_state(self):
        state = d.empty_state()
        original = copy.deepcopy(state)
        with self.assertRaises(d.DigestError):
            d.advance(state, self.items, self.cfg, NOW, MagicMock(side_effect=d.DigestError("quota")))
        self.assertEqual(state, original)

    def test_history_pruned_but_seen_kept(self):
        self.cfg.update(max_articles=1, history_items=1)
        first, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
        second, _ = d.advance(first, [], self.cfg, NOW + timedelta(days=1), summary)
        third, _ = d.advance(second, self.items, self.cfg, NOW + timedelta(days=2), MagicMock(side_effect=AssertionError()))
        self.assertEqual(len(third["history"]), 1)
        self.assertTrue(set(first["seen"]).issubset(third["seen"]))

    def test_queue_limit_fails_without_dropping_items(self):
        self.cfg["max_pending"] = 1
        state = d.empty_state()
        with self.assertRaises(d.DigestError):
            d.advance(state, self.items, self.cfg, NOW, summary)
        self.assertEqual(state, d.empty_state())

    def test_digest_uses_configured_timezone(self):
        self.cfg["timezone"] = "America/Los_Angeles"
        state, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
        self.assertEqual(state["history"][0]["date"], "2026-11-04")

    def test_unknown_omitted_and_repeated_references_rejected(self):
        for refs in [["99"], ["1"], ["1", "1", "2"]]:
            value = {"title": "T", "intro": "I", "stories": [{"headline": "H", "summary": "S", "article_ids": refs}]}
            with self.subTest(refs=refs), self.assertRaises(d.DigestError):
                d.validate_summary(value, ["1", "2"])

    def test_rss_html_escaping_and_stable_guid(self):
        malicious = summary(self.items)
        malicious["stories"][0]["summary"] = '<script>alert("x")</script> & more\x01'
        state, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, lambda _: malicious)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            d.render_site(state, self.cfg, output)
            feed = feedparser.parse((output / "feed.xml").read_bytes())
            self.assertFalse(feed.bozo)
            tree = ET.parse(output / "feed.xml")
            self.assertEqual(tree.findtext("channel/item/guid"), "daily-rss-digest:2026-11-05")
            description = tree.findtext("channel/item/description")
            self.assertIn("&lt;script&gt;", description)
            self.assertNotIn("<script>", description)
            self.assertIn('href="https://example.org/library"', description)
            self.assertNotIn("<script>", (output / "index.html").read_text())
            self.cfg["site_url"] = "https://new.example.org"
            d.render_site(state, self.cfg, output)
            self.assertEqual(ET.parse(output / "feed.xml").findtext("channel/item/guid"), "daily-rss-digest:2026-11-05")

    def test_state_roundtrip_and_corruption_rejected(self):
        state, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "state.json"
            d.save_state(file, state)
            self.assertEqual(d.load_state(file), state)
            file.write_text("{}")
            with self.assertRaises(d.DigestError):
                d.load_state(file)

    def test_partial_feed_failure_does_not_stop_healthy_feed(self):
        with patch.object(d, "download_feed", side_effect=[d.DigestError("Failed"), (self.rss, SOURCE["url"]) ]):
            articles, errors = d.collect([SOURCE, SOURCE], self.cfg, NOW)
        self.assertEqual(errors, 1)
        self.assertEqual(len(articles), 2)

    def test_total_feed_failure_is_an_error(self):
        with patch.object(d, "download_feed", side_effect=d.DigestError("Failed")):
            with self.assertRaises(d.DigestError):
                d.collect([SOURCE], self.cfg, NOW)

    def response(self, status=200, data=None, headers=None):
        result = MagicMock()
        result.__enter__.return_value = result
        result.status_code = status
        result.headers = headers or {}
        result.json.return_value = data
        return result

    def test_gemini_payload_auth_and_transient_retry(self):
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(summary(self.items))}]}}]}
        with patch.object(d.requests, "Session") as factory, patch.object(d.time, "sleep") as sleep:
            session = factory.return_value.__enter__.return_value
            session.post.side_effect = [self.response(429, headers={"Retry-After": "1"}), self.response(data=body)]
            result = d.summarize(self.items, self.cfg, "test-secret")
            self.assertEqual(result["title"], "Daily news")
            self.assertEqual(session.post.call_count, 2)
            args, kwargs = session.post.call_args
            self.assertNotIn("test-secret", args[0])
            self.assertEqual(kwargs["headers"], {"x-goog-api-key": "test-secret"})
            self.assertEqual(kwargs["json"]["generationConfig"]["responseFormat"]["text"]["mimeType"], "APPLICATION_JSON")
            self.assertFalse(kwargs["allow_redirects"])
            self.assertNotIn("test-secret", json.dumps(kwargs["json"]))
            sleep.assert_called_once()

    def test_gemini_rejects_blocked_truncated_invalid_responses(self):
        for data in [{"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": [{"finishReason": "MAX_TOKENS"}]},
                     {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not JSON"}]}}]}]:
            with self.subTest(data=data), patch.object(d.requests, "Session") as factory:
                factory.return_value.__enter__.return_value.post.return_value = self.response(data=data)
                with self.assertRaises(d.DigestError):
                    d.summarize(self.items, self.cfg, "secret")

    def test_gemini_missing_key_and_auth_error_never_leak_response(self):
        with self.assertRaises(d.DigestError):
            d.summarize(self.items, self.cfg, "")
        with patch.object(d.requests, "Session") as factory:
            session = factory.return_value.__enter__.return_value
            session.post.return_value = self.response(403, {"message": "secret"})
            with self.assertRaises(d.DigestError) as raised:
                d.summarize(self.items, self.cfg, "secret")
            self.assertNotIn("secret", str(raised.exception))
            self.assertEqual(session.post.call_count, 1)

    def test_feed_redirect_checks_destination(self):
        with patch.object(d.requests, "Session") as factory, patch.object(d, "public_url") as check:
            session = factory.return_value.__enter__.return_value
            response = self.response()
            response.iter_content.return_value = [self.rss]
            session.get.side_effect = [self.response(302, headers={"Location": "/new"}), response]
            data, final = d.download_feed("https://example.org/rss", 20)
            self.assertEqual(final, "https://example.org/new")
            self.assertEqual(data, self.rss)
            self.assertEqual(check.call_count, 2)

    def test_feed_size_limit_and_retries(self):
        with patch.object(d.requests, "Session") as factory, patch.object(d, "public_url"), patch.object(d.time, "sleep"):
            session = factory.return_value.__enter__.return_value
            session.get.side_effect = requests.Timeout("hidden sensitive URL")
            with self.assertRaises(d.DigestError):
                d.download_feed(SOURCE["url"], 20)
            self.assertEqual(session.get.call_count, 3)
            session.get.side_effect = None
            response = self.response()
            response.iter_content.return_value = [b"x" * 5_000_001]
            session.get.return_value = response
            with self.assertRaises(d.DigestError):
                d.download_feed(SOURCE["url"], 20)

    def test_demo_and_publish_only_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, state_path = Path(tmp) / "public", Path(tmp) / "state.json"
            result = subprocess.run([sys.executable, "-m", "digest", "--demo", "--output", str(output), "--state", str(state_path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(state_path.exists())
            self.assertEqual(len(ET.parse(output / "feed.xml").findall("channel/item")), 1)
            state, _ = d.advance(d.empty_state(), self.items, self.cfg, NOW, summary)
            d.save_state(state_path, state)
            before = state_path.read_bytes()
            result = subprocess.run([sys.executable, "-m", "digest", "--publish-only", "--output", str(output), "--state", str(state_path)], cwd=ROOT, env=dict(os.environ, SITE_URL=self.cfg["site_url"], GEMINI_API_KEY=""), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_bytes(), before)

    def test_configuration_validation(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "../../bad"}):
            with self.assertRaises(d.DigestError):
                d.load_config(ROOT / "config.toml")
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.toml"
            file.write_text((ROOT / "config.toml").read_text().replace(f"max_articles = {self.cfg['max_articles']}", "max_articles = -1"))
            with self.assertRaises(d.DigestError):
                d.load_config(file)


class WorkflowTests(unittest.TestCase):
    def test_workflow_permissions_dependencies_and_triggers(self):
        workflow = yaml.load((ROOT / ".github/workflows/digest.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertTrue(workflow["on"]["schedule"][0]["cron"])
        self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
        self.assertEqual(workflow["jobs"]["deploy"]["needs"], "build")
        self.assertEqual(workflow["jobs"]["deploy"]["permissions"]["id-token"], "write")
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            parsed = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for job in parsed["jobs"].values():
                for step in job["steps"]:
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"^actions/[a-z-]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
