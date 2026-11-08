# Shared Semrush reports in ManualsDump generation

The shared broker stores keyword reports separately from the ManualsDump metadata
database. A saved report is not automatically part of a generation request.
`search_metadata/shared_keyword_bridge.py` imports an explicitly staged, sealed
plan using the existing local `semrush_jobs`/`semrush_links` protocol. It makes no
provider requests, opens no browser, invokes no model, and publishes nothing.

Use the installed Python executable recorded in the installation's `runtime.json`,
set `MANUALSDUMP_WORKSPACE` to the website workspace, and run the canonical module:

```powershell
& $seoPython C:\Dev\seo-sites\tools\seo\search_metadata\shared_keyword_bridge.py `
  --period CURRENT_ARCHIVE_PERIOD --plans C:\Dev\PdfSite\artifacts\seo-research\STAGED_PLANS `
  --dry-run
```

Omit `--dry-run` only at a generation boundary. The command takes the same global
generation OS lock before opening the writable metadata database. A busy lock
stops the import without opening that database. Read-only preflight can run while
generation is active. `--db` and `--hub-db` can select explicitly configured local
stores; defaults are the shared workspace stores, which have different schemas.

Plans are files named `*-import-plan.json`, at most100 per invocation. Schema1
includes the exact public page URL, source manual/page identity, raw-content and
extracted-text hashes, shared subject/job IDs, source-backed seed provenance and
1..20 captured reports. Each report identifies its shared report/evidence hashes,
snapshot file/hash, ToolsPD origin, legacy request and candidate count. The plan's
`manifestSha256` is the canonical research hash of every other field. All files
remain under ignored workspace artifacts, never in Git.

The importer checks the active indexed archive period, full ranking protection,
source identity review state, exact page text, adopted query window and URL, shared
job completion, subject text and report links, country/language/month, snapshot
hash, raw rendered report parsing and exact saved candidate values before writing.
Missing adopted history or changed/protected source pages return explicit holds.
Different or uncertain existing legacy jobs stop the import and need inspection.

Imported evidence marks an existing page draft pending in the same transaction as
the first local report commit. Interrupted imports therefore stay pending and can
resume from the saved reports. A completed import is idempotent per plan/period.
No provider attempt is refunded, reserved or replayed. Unknown metrics and explicit
no-results reports retain their original meaning. Sol6.1 medium must review every
candidate through `keywordDecisions` before saving updated metadata; candidate
relevance and publication are never decided by this bridge.

The operational generation controller can call this command before preparing its
next groups, after any required history adoption. Already running model groups
keep their frozen inputs. A ready/imported result is not proof of completed page
generation, full-period coverage, SEO improvement or public activation.
