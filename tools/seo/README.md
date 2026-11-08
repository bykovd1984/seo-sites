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
prevent parallel collection against the same data directory. A separate machine-wide
provider lock also covers different data directories on this host. Use one common home
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

Pages with fewer than five normalized extractable text characters cannot satisfy
the existing verbatim-quote validator. They are explicitly recorded as
`skipped/source_text_unavailable` with source hash, artifact and character count,
without a model call. This reason requests image/OCR follow-up; it does not claim
metadata was generated. A changed source is reassessed by period reconciliation.
Other missing evidence and uncertain calls remain pending.

Archive reconciliation commits each assessed page separately instead of holding
the writer for the full period. Saved context-file imports acquire the write
transaction before reading/updating research state and retry only transient
SQLite lock errors, up to three attempts. Invalid evidence is not retried. A
failed file remains available for local replay; no server export, model request
or provider lookup is repeated by this retry path.

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

## Grouped ManualsDump drafts

`seo-manualsdump-groups` processes a frozen archive period, newest observations
first, with the same ChatGPT-authenticated `gpt-6.1-sol` / `medium` generator.
One call handles up to eight independent page cases by default. It retains every
disclosed query with its provider/URL scope and dates, and saves the full original
source bundles compressed alongside an immutable prompt and invocation receipt.
No paid API key, provider collection or publication is involved.

```powershell
seo-manualsdump-groups --period PERIOD_ID --pages-per-call 8 --limit 64 --run
seo-manualsdump-groups --resume-group GROUP_ID --run
seo-manualsdump-groups --repair-group GROUP_ID --run
seo-manualsdump-groups --period PERIOD_ID --repair-queue --limit 25
```

Omit `--run` to prepare a group without calling the model. Each request is reserved
atomically before dispatch; both single-page planners and grouped planners skip
reserved/held work. The shared generation OS lock covers both runners. A completed
response can be re-imported after a restart without another call; an uncertain
call remains held. Explicit repairs include only invalid held members from a known
completed call, preserve the parent evidence, and are limited to three revisions.

`--repair-queue` lists current held requests whose parent call completed and
whose immutable outputs still verify. It makes no model/provider call and excludes
resolved or obsolete requests. The returned `kind` selects the normal or source-review
repair command. Each completed invalid revision can be reconsidered up to the existing
three-revision limit; uncertain calls and exhausted repairs remain held for inspection.

Each result must cover the exact page/request identity. Source, ranking, query,
candidate and metadata checks run per page; one invalid member does not discard
valid members. Missing/duplicate request coverage holds the entire response.
Actual token usage is stored once per group, never duplicated for its pages.
All outputs remain drafts; deferred Semrush coverage remains explicit.

## Source review of flagged drafts

`seo-manualsdump-reviews` revisits `needs_review` pages using the saved introductory
pages (1 and 2, when present) of that same source manual. Supply missing source
contexts first. Review preparation makes no model/provider requests and may run
while a normal generation batch is active. Execution shares the generation lock
and the same ChatGPT-authenticated `gpt-6.1-sol` / `medium` settings.

```powershell
seo-manualsdump-reviews --period PERIOD_ID --limit 8
seo-manualsdump-reviews --resume-group GROUP_ID --run
seo-manualsdump-reviews --repair-group GROUP_ID --run
```

The second pass preserves the original draft. Introductory pages establish identity
and language; page topics, quotes, numeric claims and selected queries still have
to pass the exact target-page checks. Missing/transient source data remains pending.
A completed review that still cannot resolve the source saves a specific model
rationale and source-bound skip evidence. A skip is never inferred from the first
review flag or missing Semrush alone. Approved reviews and skips become pending
again when their target/search evidence or supporting manual pages change; run
archive reconciliation after importing corrected source contexts.

Explicit repairs retain the review baseline and introductory-page proofs. Use the
review repair command rather than the ordinary group repair route. Unknown calls
stay held. No source-review operation activates metadata or publishes a site.

Documented default LAN addresses are retained in page-query evidence when the exact
source page contains the address. Unsupported local-address strings remain filtered;
raw imported observations are preserved. Address strings are research data, never
URLs for the collector to open. IPv6 equivalent spellings are compared canonically.

Ranking eligibility uses reported page averages, with their actual report dates.
A newer query-only report cannot replace a page-average report for the same
provider/URL. Scopes without page measurements and explicit unknown page reports
remain protected, as do reported page positions below8. Query positions are never
substituted for page averages, and old measurements are not labelled current ranks.

## Completed source-export failures

After importing matching converted/legacy files from one bounded source-export run,
record an evidence-bound outcome without provider/model requests:

```sh
python tools/seo/search_metadata/research.py source-completion --converted RUN/converted-001.jsonl --legacy RUN/legacy-001.jsonl --period PERIOD_ID
```

Files must be saved workspace artifacts from the same run. The exact page must
have an explicit converted failure record, and the latest imported legacy attempt must
report a missing file, absent catalog entry, or missing storage/out-of-range page.
Converted omissions, size limits and catalog-brand ambiguity are insufficient. Version1 proofs reopen for explicit re-export. The stored reason means no verified context was exported from the approved copies;
it does not establish that the original PDF is absent. Limits, oversized files and
unknown errors stay pending. Replays do not duplicate failure events. Ranking
protection runs before skips, and actual source content takes precedence. Importing
recovered context and reconciling the period reopens a previously skipped page.
Changed attempts or damaged proof artifacts also return the page to pending.

Full outcome reconciliation shares the ManualsDump generation OS lock. Run
`archive reconcile` or `outcomes` between generation batches; a busy generation
slot rejects reconciliation before opening its research database. This prevents
a long derived-status refresh from starving the import of a completed model
response. Read-only status/coverage queries remain available while generation runs.
Saved completed group responses can be replayed with `--resume-group` without a
second model call; verify their receipt and output/event hashes first.


ToolsPD safety incidents are shared by all clients using the configured home.
Use `provider_status` before collection. `pause_provider` can stop further report
requests, and an explicit simultaneous-session warning automatically persists the
same stop. No domain failover follows that warning. Clearing an incident is an
explicit local owner action; see [provider safety recovery](PROVIDER_ACCESS.md#shared-safety-pause).


The archive source queue automatically includes missing cover/intro pages1..2 for
pending source reviews. They inherit their target's newest observation and click
priority, share the same export batch limit, and are deduplicated across reviews
and target pages. No search traffic on a cover is required. Existing source text,
known source failures and the live ranking guard are respected; only the explicit
retry flag requeues a known non-transient failure. The collector/profile and
provider safety state are unchanged.
