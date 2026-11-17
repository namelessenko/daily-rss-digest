# Ratings, photos and 17:00 scheduling

## Install this update

The update ZIP contains replacement files, not a replacement repository.
Extract it, copy the digest/, tests/, docs/ and .github/ folders and config.toml
into your existing checkout (merge folders, replace the matching files).
On macOS, Command–Shift–Period reveals .github. GitHub Desktop will show the changes.
Commit to main and push. Keep your existing feeds.opml, secrets, and digest-state branch.
No API key is included in this update.

The new digest/editorial.py file is REQUIRED alongside digest/core.py.
The new tests must be copied with the code.
Run: python -m unittest discover -s tests -v

To see the new format today: Actions → Daily RSS digest → Run workflow →
main → check replace_today only. This uses recent, previously unprocessed articles
and creates a replacement GUID. It does not rewrite the same articles with new ratings.
If there are no eligible new articles, wait for new feed entries.
Rebuilding saved history shows the new layout but cannot invent old ratings or photos.

## What changes

Priority order: consequential Ukraine war developments, European politics, world
politics, new scientific studies. Articles are shortlisted before Gemini sees them,
using transparent keyword matching with space reserved for politics and science.
This is a bounded sample of feeds, not exhaustive coverage; keyword selection may
miss relevant articles, especially in languages outside English, Ukrainian and Russian.
max_articles in config.toml controls the batch size. The supplied value remains 20.

Gemini groups coverage and assigns a category, an integer impact rating, and a reason.
5 = exceptional major impact; 4 = substantial development; 3 = useful relevant update;
2 = marginal/repetitive/speculative; 1 = irrelevant/noise.
Stories below 3 and stories categorized as other are omitted from displayed content,
but retained in saved history and marked processed. Ratings are editorial judgments,
not independent fact checking. No-news days can produce a short no-substantial-updates digest.
Change the policy in digest/editorial.py (POLICY); topic matching is in PATTERNS.

Photos are extracted from Media RSS images/thumbnails, image enclosures and article
HTML included in RSS/Atom. One feed-provided image per displayed story is linked to
its source. We do not invent photographs, scrape article pages or download image files.
If a feed supplies no usable HTTPS image, its story remains text-only. Existing saved
articles may lack image metadata. Hosts may block hotlinking; readers may block images
or remove inline styling. Stars, numeric scores, headings and source links work without CSS.
An image comes from the source feed; it may be an archive or illustrative photo, so the
caption does not assert that it depicts the reported event.

## 17:00 Europe/Berlin: what can and cannot be promised

Both digest dates and schedule timezone are now Europe/Berlin.
GitHub fallback requests runs at 17:00, 18:00 and 19:00. The first successful run
creates that date's digest; later successful runs redeploy the same feed.
GitHub can delay or drop schedules. Increasing their number is not a timing guarantee.
Gemini can fail too. Do not leave the five-minute diagnostic schedule enabled.

Recommended: have cron-job.org trigger the existing workflow at 17:00, with recovery
attempts at 17:10 and 17:20. This improves trigger observability but does NOT guarantee
publication at 17:00: GitHub runner allocation, feed fetching, Gemini and Pages deployment
still take time. An RSS reader independently chooses when to refresh.

1. Create a fine-grained GitHub token restricted to namelessenko/daily-rss-digest.
   Grant repository Actions: read and write. Record its expiry and renew it before then.
2. In cron-job.org create an enabled job with timezone Europe/Berlin, daily at 17:00.
3. Method: POST. URL:
   https://api.github.com/repos/namelessenko/daily-rss-digest/actions/workflows/digest.yml/dispatches
4. Add headers:
   Authorization: Bearer YOUR_TOKEN
   Accept: application/vnd.github+json
   Content-Type: application/json
   X-GitHub-Api-Version: 2022-11-28
5. Body: {"ref":"main"}
6. Test execution. A successful HTTP response means GitHub accepted the request;
   follow the new workflow_dispatch run in Actions and verify build AND deploy succeed.
   GitHub may label these automated API starts "Manually run".
7. Add two matching jobs at 17:10 and 17:20, and enable failure notifications.
   Scheduler alerts cover failed dispatch requests, not later Gemini/deployment failures.
   Enable GitHub Actions failure notifications as well.
8. Save the token only in the scheduler's header setting; never commit it.

If you require publication at a fixed clock time, the architecture must change:
prepare the digest before 17:00, store a validated draft, and serve the XML from an
always-running server which switches from the previous feed to the prepared draft
at 17:00 Europe/Berlin. Set a readiness alert before 17:00. If generation fails,
serve the last successful digest with its original date, never fabricate a fresh one.
GitHub Pages cannot implement that request-time release gate. Even with that server,
reader arrival cannot be guaranteed because readers poll on their own schedules.
This release does not provision an external account, server or notification service.

References:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://cron-job.org/en/
