# Verification notes

Checked **5 November 2026**. These are versioned design choices, not a promise that hosted services will never change.

## Gemini

- **Model:** `gemini-3.1-flash-lite`, an explicit non-preview ID listed by Google. It is selected for a small daily text summarization task, not claimed to be Google's newest or strongest model. [Model catalog](https://ai.google.dev/gemini-api/docs/models?hl=en) · [Pricing](https://ai.google.dev/gemini-api/docs/pricing?hl=en)
- **API:** direct HTTPS `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, with the API key in `x-goog-api-key`. No Google SDK version dependency. The Generate Content interface remains documented, although Google's navigation now labels it legacy and also promotes Interactions. [Generate Content guide](https://ai.google.dev/gemini-api/docs/generate-content?authuser=50) · [API reference](https://ai.google.dev/api/generate-content?authuser=01&hl=en)
- **Structured output:** `generationConfig.responseFormat.text` contains `mimeType: APPLICATION_JSON` and a JSON `schema`. This exact field shape and enum were also verified against Google's live [v1beta discovery document](https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta). The code does not rely on the older deprecated `responseSchema` spelling. Local validation additionally rejects omitted, repeated and invented article IDs. [Structured output guide](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- **Free use:** Google's pricing table lists free-tier text input/output for the chosen model. Limits and access vary by model, project and region. The code neither enables billing nor silently switches models. It sends no search-grounding or other paid tool requests. [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) · [Available regions](https://ai.google.dev/gemini-api/docs/available-regions) · [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations?authuser=8&hl=en)

The public discovery document verifies request structure, not your account's model access. A real authenticated Gemini completion has **not** been performed for this deliverable because no API key was supplied. The first manual workflow run verifies your key, project quota, model access and the model's actual output.

## GitHub

- Pages uses a build artifact and a dependent deployment job, with a `github-pages` environment and explicit `pages: write` / `id-token: write` on deployment. The build publishes only `public/`. [Custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- The user must choose **GitHub Actions** as the Pages source. [Publishing source settings](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- Schedules run from the default branch; UTC is the default timezone. Runs can be delayed/dropped, and inactive public repositories can have schedules disabled after 60 days. `workflow_dispatch` provides a manual trigger. [Workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- Full action commit hashes are pinned. The following hashes were resolved from the official action repositories' tags during verification:

| Action | Verified tag | Pinned commit |
| --- | --- | --- |
| [checkout](https://github.com/actions/checkout) | v7 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| [setup-python](https://github.com/actions/setup-python) | v7 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| [configure-pages](https://github.com/actions/configure-pages) | v5 | `983d7736d9b0ae728b81ab479565c72886d7745b` |
| [upload-pages-artifact](https://github.com/actions/upload-pages-artifact) | v4 | `7b1f4a764d45c48632c6b24a0339c27f5614fb0b` |
| [deploy-pages](https://github.com/actions/deploy-pages) | v4 | `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e` |

GitHub-hosted `ubuntu-latest` and Python 3.13 are used. The workflow does not depend on pushes by `GITHUB_TOKEN` triggering another workflow: state save and Pages deployment happen in the same run. Source remains on the default branch; data lives in `digest-state`. [GitHub token permissions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication)

No GitHub repository has been created or deployed as part of packaging this project. Live Pages permissions, environment rules and the resulting reader URL must be confirmed in the user's repository.

## Validation performed

See `VALIDATION.md` in this directory for the delivered build's test results and limitations. All normal tests use local fixtures, mocked HTTP responses or temporary local Git repositories. They do not consume Gemini quota.
