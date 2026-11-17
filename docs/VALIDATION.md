# Delivered build validation

Validation date: **5 November 2026**.

| Check | Result |
| --- | --- |
| Python runtime | Python 3.13, isolated virtual environment |
| Dependency installation | All pinned runtime and development dependencies installed successfully |
| Dependency consistency | `python -m pip check` passed |
| Python compilation | `python -m compileall -q digest scripts tests` passed |
| Offline test suite | **32 tests passed** |
| Actions workflow validation | **actionlint 1.7.12 passed** for both workflows; release download checksum verified |
| Offline demo | Generated RSS and HTML without an API key; no production state written |
| RSS output | Parsed with both ElementTree and feedparser; valid RSS item, stable GUID, escaped HTML and original links checked |
| Live example feeds | Both supplied public RSS/Atom URLs fetched successfully; recent entries parsed without Gemini calls |
| Gemini request structure | Request fields, structured output field and `APPLICATION_JSON` enum checked against the live Google v1beta discovery schema |
| Action revisions | Full commit hashes resolved from official action repositories |
| ZIP | Extracted project retested; required hidden workflow files included; no local state, credentials, virtual environment or caches included |

The 32 tests cover nested/duplicate OPML subscriptions, entity rejection, RSS and Atom parsing, dates, tracking URLs, unsafe links and private destinations, feed retries/redirects/size limits, partial/total feed failures, URL/GUID deduplication including transitive aliases, queue overflow and next-day processing, same-day reruns, empty days, failure rollback, retention, timezone boundaries, invalid model references, Gemini authentication and retry behavior, blocked/truncated output, HTML escaping, state roundtrip/corruption, demo/rebuild commands, configuration and workflow structure.

Three of these tests exercise the persistence script against real temporary local Git repositories: first save and restore, unchanged state, competing writer rejection, and unreachable-remote behavior. They confirm that the source branch is left intact and only `state.json` is written to the data branch.

## Not exercised with user credentials

- No authenticated Gemini generation: no user API key was provided. HTTP responses in automated tests are mocked, so account-specific access, quotas and actual summary quality remain unverified.
- No live GitHub Actions/Pages deployment: the deliverable is an uploadable ZIP, not an already configured repository. GitHub permissions, Pages settings and environment restrictions must be verified on the first manual run.
- No end-to-end subscription test in the user's RSS reader. The generated RSS was validated locally.

The project intentionally fails visibly on unavailable models, invalid summaries and rejected state writes. It does not report a successful digest when generation fails.
