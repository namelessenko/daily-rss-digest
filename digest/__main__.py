import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from .core import (UTC, DigestError, advance, collect, empty_state, load_config,
                   load_state, parse_feed, read_opml, render_site, save_state, summarize)


def main():
    parser = argparse.ArgumentParser(description="Generate a Gemini daily digest and RSS site")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--opml", type=Path, default=Path("feeds.opml"))
    parser.add_argument("--state", type=Path, default=Path(".digest-data/state.json"))
    parser.add_argument("--output", type=Path, default=Path("public"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish-only", action="store_true", help="Rebuild saved history; no feeds or Gemini calls")
    mode.add_argument("--demo", action="store_true", help="Offline fixture preview; never modifies production state")
    mode.add_argument("--replace-today", action="store_true", help="Replace today's saved digest using recent unprocessed articles")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        cfg = load_config(args.config)
        if args.demo:
            cfg["site_url"] = cfg["site_url"] or "https://example.github.io/daily-digest"
            now = datetime(2026, 11, 5, 6, 17, tzinfo=UTC)
            data = (Path(__file__).resolve().parent.parent / "tests/fixtures/sample.rss").read_bytes()
            articles = parse_feed(data, {"url": "https://example.org/feed", "title": "Demo feed"}, "https://example.org/feed", cfg, now)

            def demo_summary(items):
                return {"title": "Offline demonstration", "intro": "This preview uses fixtures and no AI service.",
                        "stories": [{"headline": a["title"], "summary": a["excerpt"] or "No excerpt supplied.",
                                     "article_ids": [str(i)]} for i, a in enumerate(items, 1)]}

            state, message = advance(empty_state(), articles, cfg, now, demo_summary)
            render_site(state, cfg, args.output)
            logging.info("%s. Demo files written; production state untouched.", message)
            return 0
        if not cfg["site_url"]:
            raise DigestError("Set SITE_URL or config.toml site_url before running locally")
        state = load_state(args.state)
        if args.publish_only:
            render_site(state, cfg, args.output)
            logging.info("Rebuilt %d saved digests without API calls", len(state["history"]))
            return 0
        now = datetime.now(UTC)
        feeds = read_opml(args.opml, cfg["max_feeds"])
        articles, failures = collect(feeds, cfg, now)
        state, message = advance(state, articles, cfg, now,
                                 lambda items: summarize(items, cfg, os.environ.get("GEMINI_API_KEY", "")),
                                 replace_today=args.replace_today)
        # Build successfully before persisting. The workflow commits state before deployment;
        # a deployment failure is recoverable via --publish-only without another AI charge.
        render_site(state, cfg, args.output)
        save_state(args.state, state)
        logging.info("%s; %d queued; %d/%d feeds failed", message, len(state["pending"]), failures, len(feeds))
        return 0
    except DigestError as error:
        logging.error("%s", error)
        return 1
    except (OSError, ValueError):
        logging.error("Cannot read/write project files or parse configuration; check paths and TOML syntax")
        return 1


if __name__ == "__main__":
    sys.exit(main())
