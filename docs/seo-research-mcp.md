# Shared SEO research MCP

The canonical source now lives in the SEO Sites repository. See
[installation and agent instructions](../tools/seo/README.md) for the packaged
runtime and Claude Code/Codex connections.

The local `seo-research` MCP and console application use the same research service.
They collect evidence and save model decisions. They never call a model, publish
content, change IIS, or write a website's production database.

## What works

- Multiple configured sites, ordinary URLs, and new topics without a URL or search history.
- Exact Google account/property and Bing property checks before read-only collection.
- Newest-day-first Google page totals and disclosed query rows, independently stored.
  Optional country/device dimensions apply to query reports, not page ranking totals.
- Bing's retained page/query snapshots with their actual API-labelled dates. These
  are not represented as a complete daily historical series.
- Normalized JSON imports from chat/file exports, labelled as supplied evidence.
- ToolsPD Keyword Magic jobs and captured-report imports; country/seed matching,
  explicit no-results, unknown metrics, and observation age remain visible.
- A shared keyword cache, global ToolsPD daily ceiling, and durable job progress.
- Bounded content/metrics reads, immutable compressed evidence bundles, and draft
  model decisions: metadata, expand_content, new_content, merge_topics, no_change,
  needs_research.
- Local stdio MCP using the official Python SDK 2.3.0. No public endpoint.

The current live ToolsPD collector remains **paused** in local configuration.
Do not turn it on merely to test MCP. The worker's new-site Google/Bing paths have
fixture coverage; new sites still require independent live account/property checks.
The owner-authorized ManualsDump credentials may be referenced for ManualsDump;
other profiles do not silently inherit those credentials.

On 6 November 2026 the local server was registered as `seo-research`, with profiles
for ManualsDump, Grammar Guru, Grammar Flashcards, DeviceClue and Równa ściana.
Only ManualsDump's existing provider bindings are enabled. No collection jobs were
queued during installation. The independent Windows worker was verified running.
The current chat may need its MCP connections refreshed or the app restarted before
the newly registered tools appear; CLI registration does not prove hot reload.

## Architecture

`research_hub_app.py` is the entry point. `research_hub/service.py` supplies the
shared operations; `mcp_server.py` and `cli.py` are adapters. `store.py` owns the
SQLite queue, compressed immutable evidence and versioned decisions. `collectors.py`
reuses the existing tested HTTP/authentication and rendered Semrush report parser
from `search_metadata`, without calling its PDF-only collectors or changing its DB.
Keep both directories when moving this tool to a separate repository.

The original ManualsDump importer, research database, generated metadata and runtime
publication mechanism remain independent. Existing research is not silently migrated.
There is no universal publisher: a website-specific adapter must apply approved
changes and recheck identity/current content/ranking before deployment.

## Install and register

Python 3.12 was used for validation. Install the SDK into an isolated environment
or the ignored `artifacts/seo-research/dependencies` directory (the launcher supports
that location, including the Windows pywin32 bootstrap):

```powershell
python -m pip install --target artifacts/seo-research/dependencies -r tools/seo/research_hub/requirements.txt
python tools/seo/research_hub_app.py init
python tools/seo/research_hub_app.py project-add grammar-example --hosts example.com --languages en ru
codex mcp add seo-research -- C:\path\to\python.exe C:\Dev\seo-sites\tools\seo\launch.py serve
```

Use the actual Python executable, not the Windows Store alias. The local config is
`artifacts/seo-research/config.private.json`; credentials are absolute file references,
never tool arguments or model-visible outputs. `config.example.json` documents its shape.
Provider bindings default to disabled. `project-add --enable-providers` is a local
configuration operation, not a live access check. It still verifies the exact account
and property on every collection run. Protect credential files with owner/SYSTEM ACLs.

## Independent worker on Windows

MCP clients can terminate their entire process tree on disconnect. Consequently the
Windows MCP does **not** spawn a collector child and pretend it is independent.
Install a normal owner process at sign-in:

```powershell
tools/seo/research_hub/install-worker.ps1 -Python C:\path\to\python.exe
```

The `SEO Research Worker` task runs at owner sign-in, without elevation or a stored
password. It has no scheduled provider imports and sends no notifications. It only
processes explicitly queued jobs and waits when idle. It requires the computer to
be running and the owner signed in. Login/restart recovery preserves search progress;
an interrupted browser attempt is held for explicit resume and is still charged
against the local daily ceiling. Remove only its startup task with the same script's
`-Remove` switch; evidence and jobs remain.

For one bounded foreground pass use `worker`; for a persistent foreground process
use `daemon`. `list_projects` reports the worker lock and heartbeat. When the worker
is absent, queueing still saves a job and explicitly reports that it has not started.
No Windows process-tree restrictions are bypassed.

## Chat workflow

1. `list_projects`, then `find_subjects` to avoid duplicating existing/planned content.
2. `save_subject` for a page or a topic; provide source text, language and status.
3. `sync_search` for a configured provider/period, or `import_search_report` for a
   normalized export. Review `job_status` and `list_datasets` for coverage.
4. `query_search` with bounded filters. Page and query metrics remain separate.
5. `research_keywords` with a subject, 1..20 seeds, country and language. The worker
   reuses fresh matching reports before considering a live lookup. `import_keyword_report`
   also accepts an already captured UI report for the exact queued job.
6. `get_keywords` / `prepare_research`. The model reviews evidence and can request
   another slice of content or more research. `save_decision` saves a draft only.

All tool operations have console equivalents, with JSON input from a file or stdin:

```powershell
python tools/seo/research_hub_app.py call projects
python tools/seo/research_hub_app.py check-mcp
python tools/seo/research_hub_app.py call put_subject --input subject.json
python tools/seo/research_hub_app.py call queue_search --input search-request.json --queue-only
python tools/seo/research_hub_app.py call bundle --input bundle-request.json
```

Example `subject.json` (no model or network call):

```json
{"project":"grammar-example","kind":"topic","title":"Present Simple exercises","language":"ru","studied_language":"en","publication_status":"draft","text":"Reviewed source notes go here."}
```

Example normalized report wrapper for `call import_search --input report.json`:

```json
{
  "project": "grammar-example",
  "report": {
    "provider": "google", "kind": "pages",
    "start": "2026-10-01", "end": "2026-10-31",
    "observedAt": "2026-11-06T00:00:00+00:00",
    "scope": {"property": "sc-domain:example.com", "searchType": "web"},
    "sourceReference": "Owner-exported GSC report",
    "coverage": {"limitation": "Supplied export; completeness not established"},
    "rows": [{"url":"https://example.com/present-simple","clicks":2,"impressions":100,"position":12}]
  }
}
```

Configure the exact Google property before importing this report. For `kind=queries`,
each row also requires `query`. Country/device, if supplied, remain separate. CSVs
with unknown scope must be normalized with explicit provenance, not guessed.
Separate pages of the same report can share `snapshotId`. Otherwise imports are
independent snapshots; a later empty snapshot supersedes older rows. Do not label
unrelated exports with the same snapshot ID.

## Evidence and limits

- Source observations, provider estimates and model decisions are separate records.
  A report's absence of keywords is not zero demand. Country volume is not global
  demand, visits, or guaranteed future traffic.
- Page rank selection uses page reports only. The optional `minimumPosition` rule
  is per project. New topics are exempt because no page exists yet. Strong pages
  remain visible for research even when editorial changes are held.
- The shared draft guard is exact-URL based. A production publisher must resolve
  canonical/AMP aliases (the existing ManualsDump publisher has its own protections).
- No overlapping date windows or engine positions are silently summed. Fresh
  snapshots supersede prior rows for the same report scope; pagination is retained
  within one snapshot. Collection is still subject to provider data limits.
- `max_requests` bounds report requests per worker pass; identity/property checks
  are additional. A partial job needs `resume_research`; errors never become done.
- Bundles contain at most 20,000 text characters and a bounded result slice. Use
  `get_subject_text`, `query_search`, and `get_keywords` to follow explicit pagination.
- Only supported, visibly verified country labels are accepted by the current
  ToolsPD parser. Unsupported databases report a blocker rather than mislabeled data.
- UI report history is current-observation evidence, not invented historical
  Semrush metrics. Old-month pending jobs require a new request.
- Web page fetching, competitor/SERP collection, GA4, HTTP hosting, universal
  publication and paid model generation are not included in this version.

## Verification

```powershell
python -m unittest discover -s tools/seo/research_hub/tests -p 'test_*.py' -v
python -m unittest discover -s tools/seo/search_metadata -p 'test_*.py'
```

Tests use synthetic providers and temporary workspace data. The MCP test uses a
real SDK stdio client/server and independent worker process, then closes MCP and
checks the worker is still alive. No live provider request, subscription purchase,
production deployment or model call is part of these tests.
