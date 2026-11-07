# SEO research application

This is the canonical source for the shared SEO MCP/CLI and the ManualsDump metadata
pipeline moved from PdfSite. Codex, Claude Code and other MCP clients use the same
service operations and shared local data directory. Agents edit and test the source
here, then reinstall the runtime to use the new wheel.

## Install

Use Python 3.11 or later with pip, setuptools and wheel. From the repository root,
initialize a private data directory for a new installation.

```sh
python -m pip install setuptools wheel
python tools/seo/research_hub_app.py --home .local/seo-research-data init
python tools/seo/install.py --home .local/seo-research-data --browser
python tools/seo/launch.py call projects
```

To reuse an existing installation, pass its data directory to `--home` and omit
`init`. The installer builds a wheel, creates a versioned environment in
`.local/seo-research/releases`, installs
dependencies and verifies a real MCP handshake. `runtime.json` records the local
launcher command and data directory. Private settings, credentials, SQLite databases,
browser profiles and build outputs are excluded from Git.

The current Windows data directory is
`C:\Dev\PdfSite\artifacts\seo-research`. It holds the existing multi-site research
store and project bindings. The ManualsDump-specific research/history databases
remain under `C:\Dev\PdfSite\artifacts\search-metadata`. They use a different schema.
Keep their existing source exports and archived evidence at their current paths.

## Claude Code

The root `.mcp.json` starts the installed runtime through the repository launcher.
Set `SEO_RESEARCH_PYTHON` to an actual Python executable if `python` is unavailable.
Approve the project server when Claude Code asks, then inspect it with `/mcp`.

For access from other projects, register the shared runtime in user scope, using
the Python executable and data directory recorded in `runtime.json`.

```powershell
claude mcp add --transport stdio --scope user seo-research -- python C:\Dev\seo-sites\tools\seo\launch.py serve
```

Replace `python` with an actual bootstrap Python executable when needed.
For Codex, use the same command after `codex mcp add seo-research --`.
Other clients can use the same stdio command and argument array.
[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

Each client starts a small MCP process. They share one SQLite store and an independent
collector worker. The database serializes writes and the worker uses an OS lock to
prevent parallel collection against the same data directory. Use one common home
on this computer. Clients on another machine using the same ToolsPD account must
connect to this central worker host; they must not start an independent browser
collector for the same account. See [the provider-access contract](PROVIDER_ACCESS.md).

Each installation writes a new release and atomically updates `runtime.json` after
the handshake passes. Existing clients can finish using their previous release.
Restart the independent collector after an upgrade to load the new worker code.

## Agent workflow

1. Call `list_projects`, then `find_subjects` to locate existing pages and planned topics.
2. Save the exact page/source text with `save_subject`, including language and publication status.
3. Use `sync_search` to queue an approved provider and date range, or import a saved export.
4. Inspect `job_status` and `list_datasets`. Resume partial work with `resume_research`.
5. Read `query_search` for current and historical queries. Preserve their dates, source and scope.
6. Queue relevant Semrush seeds with `research_keywords`, then inspect `get_keywords`.
7. Call `prepare_research`, inspect any truncation and retrieve remaining slices.
8. Analyze the evidence in the calling model and save a draft with `save_decision`.

Semrush follows the existing local enabled/paused configuration. An owner login is
available with `python tools/seo/launch.py toolspd-login`. Existing approval and
provider bindings apply to their configured sites. Check them before initiating
collection for another site.

ToolsPD uses one private `toolspd-profile` under the configured data directory.
Set `semrush.account` to the authorized Google email and `semrush.memberUser` to
its ToolsPD UserID in `config.private.json`. If the report session expires, both
collectors use the saved Google session, verify the member identity, discover the
three visible Semrush access options and try them in order. Each additional report
lookup consumes another daily attempt and observes the configured delay. Report
query, country, month, columns and final ToolsPD origin are validated before saving.
Google password/2FA prompts, security refusals and CAPTCHA require owner action;
the application stops with a specific reason instead of repeating login attempts.

`python tools/seo/launch.py toolspd-session` verifies member login and lists the
advertised service origins without requesting a keyword report. `catalogReady`
does not prove report availability. Close any owner login window before collection;
clients must share the same data directory and avoid concurrent profile use.
A separate `toolspd-dispatches.sqlite3` beside the profile records the actual
report-navigation boundary. The delay is enforced there across jobs and clients,
after authentication; reservation timestamps are not dispatch timestamps. Failed
attempts stay in the budget. Future terminal capture snapshots and session events
are archived under the job progress field `failureEvidence`, including failures
before successful failover. Reuse requires strict query/country/month validation;
missing reports and unauthenticated screens never become invented keyword data.

The ManualsDump CLI defaults to the same shared profile. No cookies or passwords
are copied from another browser profile.

When moving a running legacy batch to the shared collector, reconcile its real
attempts with `python tools/seo/launch.py import-toolspd-attempts --database PATH
--day YYYY-MM-DD`. This reads the legacy database without modifying it, preserves
provenance in compressed evidence, and idempotently counts those attempts against
the shared limit. Continue provider collection through the shared worker afterward;
the legacy CLI retains a separate ledger and must not collect concurrently.

Console operations accept JSON files and match the MCP operations.

```sh
python tools/seo/launch.py call projects
python tools/seo/launch.py call subjects --input request.json
python tools/seo/launch.py call search_rows --input request.json
python tools/seo/launch.py check-mcp
```

## ManualsDump metadata

The existing importer, archive-only mode, Sol 6.1 medium requests, historical-query
evidence and per-page outcome reconciliation are in `search_metadata`.
The installed `seo-manualsdump` command exposes `app.py`.
ManualsDump generation requests specify Codex Sol 6.1 medium. Preserve the actual
model provenance when importing those responses. Claude Code can use the shared
research tools and save its own drafts through `save_decision`.
Set `MANUALSDUMP_WORKSPACE=C:\Dev\PdfSite` when using the original local data.
The code and tests live here. IIS context-export and publication adapters remain
with the PdfSite website, where their deployment-specific settings belong.
See [the workflow guide](../../docs/search-metadata.md).

## Complete saved-history periods

The ManualsDump source console can freeze and index the entire requested provider
period without emitting a separate JSON file for each daily page observation.
Use `MANUALSDUMP_WORKSPACE` to select the existing PdfSite data directory. These
commands make no provider requests and do not invoke a model.

```sh
python tools/seo/search_metadata/app.py archive index --start 2009-01-01 --end 2026-11-07
python tools/seo/search_metadata/app.py archive status --period PERIOD_ID
python tools/seo/search_metadata/app.py archive hydrate --period PERIOD_ID --limit 100
python tools/seo/search_metadata/app.py archive context-queue --period PERIOD_ID --limit 100
python tools/seo/search_metadata/app.py archive reconcile --period PERIOD_ID
```

Indexing makes a coherent content-addressed SQLite snapshot and a manifest. The
catalogue covers every discovered manual page, including older and zero-click
observations. It retains each provider/URL's latest page average within the period,
protects any top-ranking alias, and labels missing page averages explicitly.
Historical ranks keep their dates. The processing queue is newest first and does
not shrink to the last week or to pages with clicks.

`hydrate` transfers every archived metric and disclosed query window for selected
pages into the existing research pipeline. One compressed proof batch covers many
pages/windows; original dates, providers and URL aliases remain distinct. Each
page commits atomically and retries leave completed pages out of the queue. The
frozen database hash and query-collection checkpoints are checked before import.
A batch reaching its evidence-size bound continues with the remaining pages on
the next invocation, without truncating a selected page's history.

The IIS-specific adapter remains in PdfSite:
`tools/seo/Export-ResearchContexts.ps1 -ArchivePeriod PERIOD_ID -Limit 100`. It
fetches exact guarded source HTML for this catalogue, including impression-only
pages. Continue the normal Semrush/model stages after contexts are imported.

The owner can explicitly defer Semrush enrichment for drafts:

```sh
python tools/seo/search_metadata/model_stage.py draft-policy --allow-missing-semrush
python tools/seo/search_metadata/model_stage.py queue --limit 10
```

This policy persists in the selected research database and applies to period
reconciliation too. It preserves completed keyword reports, omits unfinished
results and freezes their IDs/statuses in `researchCoverage`. Missing evidence
never means zero demand or an explicit no-results finding. Validated metadata is
stored as a draft with `draftOnly: true`; activation remains blocked. When the
missing reports arrive, the changed evidence produces a new generation request.
`draft-policy --require-semrush` restores the strict prerequisite. Source identity,
HTML hash, ranking protection and exact selected-query checks remain mandatory.

`reconcile` counts only a validated draft matching the current Sol 6.1 medium
request. Pages waiting for content, evidence or generation remain pending.

Do not restart the shared Semrush collector during another project's reserved
batch. Legacy and shared ledgers must be reconciled before moving collection
between them; archive/context preparation can continue independently.

## Codex draft batches

`seo-manualsdump-drafts` prepares source-bound requests from a complete saved
archive period. Set `MANUALSDUMP_WORKSPACE` to the existing PdfSite data root.
Only eligible, pending catalogue rows with their full page history already
imported are selected, newest first. The default prepares ten pages without a
model call; `--run` explicitly invokes Codex Sol 6.1 medium through the existing
ChatGPT sign-in, without an OpenAI API key. It never contacts ToolsPD or publishes.

```sh
seo-manualsdump-drafts --period PERIOD_ID --limit 10
seo-manualsdump-drafts --period PERIOD_ID --limit 100 --run
```

The source equivalent is `python tools/seo/search_metadata/codex_drafts.py` with
the same arguments. Each page gets an ephemeral Codex session, with user config,
project documents and memories disabled. All disclosed query strings remain in
the prompt, with provider/URL scope, first/last dates and dated last observations;
no overlapping metrics are summed. Original full windows remain in the immutable
bundle. Completed Semrush evidence is retained and missing enrichment is labelled.

A shared OS file lock prevents overlapping ManualsDump generation batches. The
runner saves the frozen bundle, prompt, strict response schema, actual invocation,
response hash and Codex events before importing a draft. Restart reuses completed
outputs and excludes already generated requests. Interrupted/failed model calls
are held for reconciliation rather than automatically charged again. Responses
with tool use, missing candidate decisions, stale inputs, wrong model/effort or
unsupported source facts cannot enter the validated draft store. Review-required
outputs remain separate. Missing source context or uncertain calls stay pending;
they do not silently count as completed pages.

A known completed response that fails validation can be explicitly repaired:

```sh
seo-manualsdump-drafts --period PERIOD_ID --directory ORIGINAL_RUN_DIRECTORY --repair-request REQUEST_ID --revision 1 --run
```

Repeat `--repair-request` for up to 25 distinct requests to repair them sequentially
and reconcile the period once. The command rechecks the exact eligible period,
current source/evidence and parent response hash. Uncertain calls, already generated requests and valid saved
responses are refused. Revisions 1..3 have separate immutable inputs, receipts and
outputs; the original response is preserved. Validation feedback emphasizes
contiguous source quotes, unchanged numeric spellings and plain metadata. New
receipts also bind the prompt and bundle hashes. No repair activates metadata.

## Worker and verification

For a foreground collector, run `python tools/seo/launch.py daemon` in a separate
process. Windows sign-in startup is managed by `research_hub/install-worker.ps1`.
Its data directory must match the one all MCP clients use.

After installation, run these checks from the repository root.

```sh
python -m unittest discover -s tools/seo/search_metadata
python -m unittest discover -s tools/seo/research_hub/tests
python tools/seo/launch.py check-mcp
```

Use the installed virtual environment's Python for the MCP tests. Fixtures cover
imports, page guards, history, keyword decisions, resumability and SDK stdio calls.
