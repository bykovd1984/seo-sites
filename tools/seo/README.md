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
on this computer. A client on another machine needs its own installation and explicitly
configured provider access.

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
