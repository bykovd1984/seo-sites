# Search-driven page metadata

Canonical application source is maintained in SEO Sites under `tools/seo`.
See [installation and agent instructions](../tools/seo/README.md).
For the existing Windows research data, set `MANUALSDUMP_WORKSPACE=C:\Dev\PdfSite`
before running the ManualsDump entry points from SEO Sites.
IIS source-export and website publication adapters live in the PdfSite repository.

For the shared multi-site MCP and console service, see
[Shared SEO research MCP](seo-research-mcp.md). It uses a separate evidence store;
the ManualsDump-specific importer and runtime publication below remain unchanged.

## Active importer / Sol goal

The workflow agreed on 2026-11-07 uses the console application to import GSC and
Bing page metrics and queries for the requested period and collect available
Semrush evidence through ToolsPD. The application saves the evidence and queues
eligible pages in order of their most recent observations. Codex `gpt-6.1-sol`
with reasoning effort `medium` analyzes
new/changed per-page evidence together with the exact manual text, selects relevant
keywords and generates titles, H1 and descriptions. Unchanged pages should not
consume another model run. The website reads prepared metadata with priority over
parser output. Production remains protected and shared-test deployment requires
coordination with headings work.

Pilot scope refined by the user: only pages with a reported average page position
of **8 or worse** may be optimized. Positions below 8 are protected. The boundary
is inclusive (8.0 qualifies); missing/invalid page positions and zero-impression
reports do not qualify. This is a selection rule, not a ranking-outcome guarantee.

Terra High collection/review records from the earlier pilot remain valid evidence;
Terra is no longer a mandatory stage of the requested importer. `app.py` and
`model_stage.py` implement the direct importer -> Sol workflow. `semrush_workflow.py
review` is retained for the optional legacy Terra workflow. The current model
handoff includes unreviewed API candidates and validates Sol's keyword decisions
and metadata together against an immutable input snapshot.
Provider retention, missing/anonymized query rows and Semrush metric snapshot dates
must remain explicit; a requested historical range is not a claim that every
provider supplies all of it. Existing scripts do not independently invoke a paid
model API or promise unattended model execution after the session ends.

## Application commands

Python 3.11+ is required. Run these commands from the repository root. A dry run
previews the period and providers without reading credentials, making API calls or
opening the databases:

```powershell
python tools/seo/search_metadata/app.py import --start 2026-10-01 --end 2026-11-03 --provider both --dry-run
python tools/seo/search_metadata/app.py prepare --limit 10
python tools/seo/search_metadata/app.py generation artifacts/search-metadata/sol-response.json
python tools/seo/search_metadata/app.py status
```

After explicit API-use approval and private credential configuration, remove
`--dry-run` and add `--approved-api-use`. Import accepts `--max-days`, `--max-pages`
and `--history-limit` for bounded, resumable batches. Google query collection,
exact-page aggregate collection and research ingestion have independent durable
checkpoints. Only saved windows inside the requested period are transferred;
repeating the same import does not duplicate unchanged observations. Import does
not run a model. `prepare` emits immutable Sol bundles; `generation` validates and
stores the separately produced model response. Website publication stays separate.

`status` also reports whether the three credential inputs are configured, using
booleans only. It does not read key values into the output or test live access.

For Google, supply `--gsc-credentials` or `MANUALSDUMP_GSC_CREDENTIALS`, or use the
ignored default `artifacts/search-metadata/credentials/google.private.json`,
containing an authorized-user refresh token for `debsites2@gmail.com`. No generic translation
service-account credential fallback is used. The application verifies the Google
email through UserInfo, then verifies access to the exact requested property. OAuth
must include email/OpenID access in addition to Search Console read-only scope.
An existing refresh token without email access will be refused, rather than being
assumed to belong to the correct account. Bing uses `BING_WEBMASTER_API_KEY` and
verifies exact property access before collection. Provider failures are recorded
separately and cannot be represented as complete history.

Bing and Semrush can also use local credential files via `--bing-credentials` /
`--semrush-credentials`, `MANUALSDUMP_BING_CREDENTIALS` /
`MANUALSDUMP_SEMRUSH_CREDENTIALS`, or the ignored default files under
`artifacts/search-metadata/credentials/<provider>.private.json`. The JSON contains
`provider` and `api_key`; a file for a different provider is refused. Keys are not
passed on command lines. Restrict these files to the current user and SYSTEM.

On 2026-11-06 the user explicitly authorized browser key generation and API use for
the test. Bing key creation succeeded in the built-in browser, and `GetUserSites`
verified the exact `https://manualsdump.com/` property. A live bounded Bing import
checked ten pages for the requested 2026-10-29 through 2026-11-04 range. It saved 96
page aggregate records and 188 disclosed query rows across four page windows; the
API-labelled query date was 2026-10-30. This is retained-snapshot evidence, not a
claim of complete daily history or successful query collection for all ten pages.
The key is in an ignored local file with user/SYSTEM-only ACL. No Semrush units
were reserved or spent and no website deployment occurred.

The old Google OAuth project is inaccessible in Cloud Console to both signed-in
accounts. After explicit approval, `ManualsDump SEO Test` was created under
`debsites2@gmail.com` on 2026-11-06: project ID `manualsdump-seo-test`, project
number `339154028487`. Search Console API is enabled. Cloud Console explicitly
reports that the project has no billing account. The user approved Google's API
Services User Data Policy and OAuth configuration was created. The Desktop app
client `ManualsDump SEO Importer` is configured; its secret is stored in an ignored
local file with user/SYSTEM-only ACL. It was initially External/Testing with
only `debsites2@gmail.com` listed as a test user. Selected scopes are read-only
Search Console, email and OpenID; no write scopes were selected. After the user's
explicit final consent, the offline token was saved locally with user/SYSTEM-only
ACL. The helper verified the exact account before saving it, and the importer
independently verified the account and exact `https://manualsdump.com/` property.
A live 2026-11-03 test saved 130 page-inventory rows, 38 disclosed page/query rows
and ten separately queried page aggregates. The bounded transfer saved 100 page
windows/inventories/rankings in the research database; remaining saved records
can be transferred on a later batch. This is one day's returned evidence, not
complete site history. No model ran, no new metadata was published and no Semrush
units were spent by this import. The report is
`artifacts/search-metadata/live-api-test-20261106/google/import-status.json`.
After the user approved the public documents and long-term authorization on
2026-11-06, the two information pages were published under the isolated test
site's `/seo-importer/` directory and verified externally. Its application assembly
and databases were unchanged; the production website was not deployed. Google
Branding now points to that public homepage/privacy policy. The exact OAuth
project was switched to **In production**. A newly authorized token was accepted
with `--require-no-expiry`, verified through an independent refresh, exact account
and property check, and a one-row Search Analytics request. Google reported no
`refresh_token_expires_in`. It atomically replaced the active ignored credential;
the earlier test grant remains in a restricted backup. Both have user/SYSTEM-only
ACL. No billing account was linked.

This removes the fixed seven-day Testing expiry. It is not an irrevocable token:
Google's [OAuth documentation](https://developers.google.com/identity/protocols/oauth2#expiration)
still allows revocation, expiry after six months of inactivity and other account
policy events. Evidence is in
`artifacts/search-metadata/google-long-term-20261106/{published.jsonl,access-check.json,oauth-production.png}`.
`authorize_google.py --client-secrets <desktop-client.json> --account
debsites2@gmail.com --output <private-file.json>` accepts the new Desktop app
client and requests only read-only Search Console plus email/OpenID. Add
`--require-no-expiry` when replacing a long-term grant; the helper refuses any
explicit refresh-token lifetime and never overwrites an existing credential. It verifies
the exact account before saving the offline grant to a restricted local file.
The user confirmed that Semrush access is only through ToolsPD.
Do not create a separate official Semrush account, attempt a shared-account API
key, or purchase API entitlement. The ToolsPD browser worker described below reads
rendered reports through the owner's authorized session, without private API calls.
Official Semrush sign-in was rejected before any authentication occurred; the
offered `debmobiledev@gmail.com` login is not to be attempted again under this scope.
This limitation does not invalidate the completed Google/Bing API access tests.

## ToolsPD Semrush worker

`app.py import` now plans ToolsPD lookups by default. `semrush plan` can also build
the queue from saved evidence. Matching unspent API plans are retained as
`superseded` and replaced by explicitly labelled UI jobs; completed API evidence
and reserved API charges are never overwritten. The API collector cannot execute
UI jobs. Explicit `--semrush-source api` is required for the optional paid route.

```powershell
python -m pip install --target artifacts/search-metadata/browser-deps -r tools/seo/search_metadata/requirements-browser.txt
python tools/seo/search_metadata/app.py semrush login --approved-browser-use
python tools/seo/search_metadata/app.py semrush plan --limit 10 --seeds 2
python tools/seo/search_metadata/app.py semrush queue --limit 5
python tools/seo/search_metadata/app.py semrush run --approved-browser-use --limit 5 --daily-limit 20 --delay 15
python tools/seo/search_metadata/app.py semrush status
python tools/seo/search_metadata/app.py prepare --limit 10
```

The worker uses installed Microsoft Edge by default (`--channel chrome` is also
supported) and an isolated profile under ignored artifacts, restricted to the
current user and SYSTEM. Its first login is interactive: sign in to ToolsPD and
open Access Semrush 1, then return to the console. Credentials must not be entered
in the console/chat. The chat's built-in browser session is not copied into this
profile. Subsequent batches use this profile without a model. `--origin` selects
another authorized HTTPS ToolsPD subdomain if the provider changes its host;
changing it requires the corresponding authenticated browser session.

The worker collects up to 100 rendered Keyword Magic Tool rows per lookup and
waits at least ten seconds between lookups. The default local UTC-day ceiling is
20 attempts. A durable SQLite reservation is committed before navigation, so
restarts and manual retries do not reset that ceiling. It is not a measurement of
the account's total quota consumed by other browser sessions. Login prompts,
challenges, provider errors and exhausted limits stop the batch. A crash leaves
the lookup reserved, rather than repeating it silently. After resolving the
issue, use `semrush retry --job <id>` explicitly.

`capture_semrush_ui.js` reads rendered report content only: no cookies, hidden
application data, intercepted requests, export paywall bypass or shared API keys.
`toolspd.py` verifies the exact heading/seed, source URL, country displayed in the
UI and observation month. Missing volume/KD stays null. Country volume is not
global demand, CPC is not organic competition, and the displayed update label is
retained without inventing a metric snapshot date. Explicit “Nothing found” is
stored separately from provider failures and does not imply zero demand. Current
content and the position >= 8 rule are checked again before results are attached.
Sol must review each imported candidate against the actual page content.

On 2026-11-06 the same extraction script was checked through the authenticated
built-in browser. `abit nf7` returned 100 US rows; `abit nf7 pins` explicitly
returned no results. Both reports were imported into the real research database,
a repeated import added nothing, and a 101-candidate Sol input was prepared for
source 146403/page 1. No metadata was generated or deployed by these imports.
Evidence: `artifacts/search-metadata/toolspd-live-20261106/`. Playwright 1.64.1 is
installed in the ignored dependency folder. Full standalone collection remains
unverified until the owner completes the one-time login in its isolated profile.

Semrush jobs are planned for relevant pages with evidence inside the requested
period. Actual paid collection is disabled by default; `--semrush-source api --semrush-units 1000`
enables a cumulative ceiling only after explicit approval and `SEMRUSH_API_KEY`
setup. `--related-limit 5` optionally requests deprecated v3 expansion. The ceiling
does not reset between runs. Semrush metrics use the current monthly snapshot,
independently of the historical GSC/Bing window, and are labelled with their actual
snapshot/observation dates. Exact page source contexts must already be in research,
or may be supplied with `--contexts`; the existing guarded source exporter remains
available for preparing those contexts.

Schema-v2 model bundles use `pipeline: import_then_sol`. Sol returns the existing
metadata fields plus a string list `selectedKeywords` and `keywordDecisions` for
every `semrushCandidates` entry. Each decision includes `candidateId`, `decision`
(`keep`, `reject`, `no_results`), `reason`, and verbatim `contentEvidence` for kept
candidates. Missing, invented or duplicate decisions are refused. Rejected or
unobserved selected keywords are refused. A provider no-results report is kept
distinct from a zero-volume measurement. Decisions are stored with the validated
metadata version in `research_model_keyword_decisions`; a separate Terra review
is unnecessary and no synthetic Terra record is created. Unchanged input reuses
the same request and generated pages leave the queue.

Verification on 2026-11-06: the application dry run for 2026-10-01 through
2026-11-03 succeeded with zero API calls. A real schema-v2 Lifebreath page-32 draft
from previously saved provider evidence was validated through the single-model
path at saved page position 9.67. This proves local model handoff/validation only;
fresh provider API collection and website deployment are still unverified.

### Pages with undisclosed queries

Google collection now has a separate paginated page inventory (`dimensions:
[page]`) with its own daily checkpoint. Query collection cannot act as the page
inventory because some traffic has no disclosed query rows. Exact-page aggregate
lookups consider pages discovered by either source. The page inventory retains
its top-row/cap limitations and does not prove complete provider history.

Saved API page aggregates also enter the discovery inventory, with independent
page clicks/impressions and raw proof. If a Google query batch is finished but has
no rows for a discovered URL, its imported search window has an explicitly empty
disclosed-query subset. This does not mean that no searches occurred, or establish
whether privacy, row caps or another omission caused the empty subset. No query
string or query-level clicks are manufactured.

The source-context queue covers both unresolved discovery rows and already
imported API windows lacking source text. A guarded source export can resolve the
specific technical `api_source_mapping_pending` hold only when source ID, page,
page count, format/manual ID and declared read-only provenance match. The source
artifact and content hash are carried into the frozen bundle's identity resolution.
Explicit catalog/content identity quarantines remain held.

For pages with clicks but no disclosed queries, Semrush lookup seeds can come from
the actual source headings and catalog identity. They are labelled `content_derived`
in `semrush_seed_sources` and model bundles, with zero attributed query clicks and
their source artifact/hash. They are never relabelled as observed search terms.
Sol still reviews every returned candidate against the page and can produce neutral
metadata with an empty selected-keyword list when demand is unknown.

An offline integration test covers page-only provider data -> saved discovery ->
guarded source context -> labelled Semrush seed -> Sol decisions/metadata -> local
runtime export. Provider and model responses in that integration test are fixtures;
it is not evidence of a live provider import.

`tools/seo/search_metadata/research.py` stores progress in `artifacts/search-metadata/research.sqlite3`. Its prefixed tables retain inventory exports, page-filtered query windows, country-specific Semrush candidates, archived evidence hashes, compressed exact page contexts, immutable model requests and versioned responses. Raw browser exports are also retained under `artifacts/seo-research-20261105`. These local artifacts are ignored by Git.

The discovery queue processes clicked pages in newer periods first. Global page inventories are used only to discover pages; their global query tables are never assigned to individual pages. A GSC query export must itself prove the exact page filter and date range. Bing CSV exports require a saved page-filter proof because their CSV lacks the landing-page column. Page totals and disclosed query totals stay separate. Bing average positions are read from `Avg. Position`, preserving missing values rather than inventing rank zero. AMP and regular query reports retain separate URL provenance; overlap selection is per provider and reported URL, so one alias does not hide another's disclosed queries.

```
python tools/seo/search_metadata/research.py inventory <gsc-inventory.zip> --start 2026-11-01 --end 2026-11-03
python tools/seo/search_metadata/research.py research-queue --limit 25
python tools/seo/search_metadata/research.py import <terra-page-manifest.json>
python tools/seo/search_metadata/research.py contexts <read-only-source-contexts.jsonl>
python tools/seo/search_metadata/research.py queue --limit 25 --directory artifacts/seo-research-20261105/bundles
python tools/seo/search_metadata/research.py generation <sol-response.json>
python tools/seo/search_metadata/research.py status
```

Terra can save unfinished research without losing the page. Generation waits for exact converted source content and an actual Semrush lookup. Explicit `Nothing found` is a completed lookup with missing metrics; it does not imply zero demand. Reported volume is tied to its country database, while unknown metric age and refresh notices remain quality warnings. Content-derived keyword seeds are explicitly distinguished from disclosed search queries. A page with clicks and no disclosed query can receive neutral, content-supported metadata, but the generator must not invent its traffic keywords.

The Sol response records model/effort, request ID, title, H1, description, selected and rejected keywords, rationale, verbatim content excerpts and `requiresReview`. Validation rejects unsupported numeric claims, changed source HTML and mismatched page identity. Review-required or partial-research responses cannot activate automatically. Generated versions remain in SQLite even when a later version replaces them. Unchanged completed requests leave the queue; changed evidence or source content creates a new request. Canonical request signatures ignore evidence-list order, so a SQL index or equal-date row reordering does not trigger another model run. Existing immutable requests are reused during this migration. A separate local runtime directory can be written using `generation --activate-directory <directory>`; this does not deploy it to a website.

Both regular and AMP views render a valid SEO H1 exactly, avoiding an additional catalog-brand prefix. The existing brand/title rendering remains the fallback. The website reads one compact metadata file per page and never queries this research database, Semrush, GSC, Bing or a model while serving a request.

Legacy regular manual pages now also check the metadata store after loading their page text. The hash is based on the same 4096-byte chunk decoding as the legacy renderer, including any leading BOM. Hashing is skipped when the store is disabled. Download pages keep their existing metadata. Legacy AMP routing continues to use its existing behavior. Two legacy routes were checked using test-only metadata in the stopped-after-use loopback instance: title/H1/description matched, and both a missing record and a mismatched hash restored the original heading. The build and HTTP results are recorded in `site-build-legacy-check.jsonl` and `isolated-legacy-http-check.jsonl`; neither shared test nor production was switched. These checks use fixtures, not published SEO drafts.

`tools/server-diagnostics/export-legacy-search-context.ps1` accepts a base64-encoded UTF-8 JSON array of `{sourcePdfId,page}` items and exports up to 200 requested identities from the guarded test catalog. Duplicate identities are skipped, order is retained, and unavailable files or limits produce explicit records. Each file is limited to 2 MiB and the batch to 64 MiB decoded text; retry remaining identities in a smaller batch. The exporter performs SELECT queries and reads files; its database connection is not enforced read-only by the database. Imported contexts are attached when their page is subsequently discovered; converted contexts take precedence over legacy examples. The runtime content hash remains the final check that the chosen source matches the page actually served. A four-identity test yielded three source records and one explicit missing-catalog result; two matched earlier source exports byte for byte.

`tools/seo/Export-ResearchContexts.ps1 -Limit 25` prepares source texts for pending research pages, preferring the converted catalog and falling back to the legacy catalog. It records unavailable legacy sources, skips those on subsequent runs, and retries them with `-RetryUnavailable`; batch-size deferrals remain retryable automatically. Each run saves its own source exports. This prepares evidence only: it does not collect missing page-filtered search reports, validate Semrush keywords, generate metadata, or deploy. Its first live batch saved nine converted and one legacy context from the isolated test catalogs.

Validation of eleven Sol drafts passed on all twenty-two regular/AMP IIS responses, including Turkish text, using an isolated loopback instance: fourteen checks in the first batch and eight for the four new pages. Its files and dependency libraries were restored and its site/pool stopped afterward. The public test release and production release were unchanged. The site/Razor build passed with zero errors and 170 warnings; 30 Python pipeline checks passed. Evidence is in `artifacts/seo-research-20261105/isolated-sol-http-check.jsonl`, `isolated-sol-batch2-http-check.jsonl` and `site-build-check.jsonl`. Initial check failures exposed older dependency libraries and metadata-directory read permissions in the private harness; the final check uses the exact compiled dependencies and grants only the private worker read access. Windows PowerShell reads metadata explicitly as UTF-8.

Identity review is a hard gate. A discovered HP-labelled DB-102 page contains Kerr Scotty furnace text; another IBM page has no available converted context. Both remain held rather than inheriting a search query's assumptions. Corrected manifests remain immutable versions; an explicit later identity resolution can clear the hold. A missing source ID may be retained as unresolved discovery evidence but cannot enter normal generation.

Full provider history is still incomplete. Browser GSC access was verified as `debsites2@gmail.com` on `https://manualsdump.com/`. The old Google OAuth application could not be used; the newly authorized test project and its remaining OAuth setup are described above. The unrelated translation service account is not a substitute. Bing key creation and a bounded live import succeeded on 2026-11-06. A successful pilot does not mean site-wide collection or production activation is complete.

This is a third source of page metadata alongside the existing parser/title flow. It does not change the manual contents or its table of contents.

Priority in both regular and AMP manual pages:

1. Active search metadata matching the exact source PDF ID, page and SHA-256 of the current converted HTML.
2. Existing `SeoService` override, when available.
3. Existing title generation (including whichever heading parser supplies its data).

`SearchMetadataStore` reads one file on demand. It never loads search history into the web process and never contacts search providers during a page request. The pilot local file reader's timings are recorded separately from full website response time. Razor encodes H1 and metadata attributes.

## Storage and activation

The collector uses SQLite for observations, API checkpoints and generation decisions. Keep it outside `wwwroot`. A deploy-independent directory stores compact runtime files:

```
<directory>/<sourcePdfId modulo 1000, padded to 3 digits>/<sourcePdfId>/<page>.json
```

Set `ManualsDump:SearchMetadata:Directory` in the site's private runtime configuration to activate that directory. Leave it unset to use existing behavior. Files contain schemaVersion, status, sourcePdfId, page, contentSha256, pageTitle, h1Heading, pageDescription and evidenceThrough. Publishing replaces each file atomically. Updates take effect without restarting the site. To roll back one page, move its file out of this directory. Invalid, oversized, draft, mismatched or stale-content records fall back. The runtime allows at most 16 KiB per record.

No production deployment or runtime configuration change is included in the pilot. The context exporter deliberately checks the isolated test database. Do not point it at production by just removing that guard; first configure an explicit read-only source connection and verify the content corresponds to the target site.

## Collection and recovery

Use Python 3.11+; service-account authentication additionally needs the installed `cryptography` package. Other pipeline functions use the standard library.

```
python tools/seo/search_metadata/main.py access
python tools/seo/search_metadata/main.py collect --engine google --start 2025-07-05 --max-days 14
python tools/seo/search_metadata/main.py collect --engine bing --start 2025-07-05 --max-pages 50
python tools/seo/search_metadata/main.py queue --limit 100 --output artifacts/search-metadata/context-queue.json
```

Choose the actual earliest retained date; the example date is not a promise that the provider still retains it. Collection defaults to ending three days before the current UTC date. GSC dates are reported in Pacific time. Each GSC day is collected newest first, including pagination, with dataState=final and page/query dimensions. Each committed batch updates its checkpoint in the same SQLite transaction. Repeating the command resumes unfinished work and advances to older days. A complete day is not fetched again automatically; to refresh corrected historical metrics, remove that day's local checkpoint explicitly after stopping the job. Neither token expiry nor an HTTP failure advances a checkpoint.

Bing supplies GetPageStats and per-page GetPageQueryStats snapshots. Its endpoint has no arbitrary start/end or paging parameters: the collector filters the dates actually returned and prioritizes pages with recent data. It does not fabricate older history. Query positions remain separate for each engine. Raw URL aliases remain in the evidence while AMP/www/slug variants map to the same source PDF/page.

Configure `GOOGLE_APPLICATION_CREDENTIALS` with a service_account or authorized_user JSON credential that can read the ManualsDump GSC property. Configure `BING_WEBMASTER_API_KEY` in the job's environment. Do not commit credentials or pass tokens in command lines. `access` tests actual property visibility. Browser login alone does not authorize unattended API collection.

GSC returns top rows and omits some queries; even a fully paginated response does not prove all traffic was exported. Reaching 50,000 rows in one day is recorded as possibly truncated. Missing data means unobserved, not zero traffic. Search clicks are not all site visits or a count of unique people. Bing's retained snapshot and UI exports may also be limited. Never join an independent global query list to an independent page list.

## Generation

The context queue advances from recent observations to older ones, focusing on pages with observed search clicks. `queue --include-impressions` also includes pages without clicks for a separate review of opportunities. Completed/reviewed pages leave the queue; new or changed metrics requeue them. Identical retries do not create duplicate facts or requeue unchanged pages. Use `queue --recheck` after reconverting content or to retry pages with unavailable context. The runtime content hash rejects old metadata in the meantime.

The server helper exports product identity, existing headings and original converted page HTML from the isolated test database/files with read-only PostgreSQL transactions. Source PDF IDs are resolved through SourceManualId, never by assuming they equal internal manual IDs.

```
./tools/seo/Sync-SearchMetadata.ps1 -Python <python.exe> -EarliestDate 2025-07-05
```

This bounded job collects available evidence, exports up to 100 source contexts, and generates files locally. Run it again to continue. Increase the explicit limits for an initial backfill. It uses a single-writer mutex. It reports provider failures and leaves checkpoints intact; it does not claim the history is complete when access fails. It does not upload the generated files or modify the live site. The context export uses the existing trusted SSH helper and test-only guard.

Only queries with clicks and at least five impressions can currently activate a generated record. Query intent must match page text; product/model numbers must agree. A matching content heading supplies the topic, or a short query phrase occurring verbatim on the page can supply it independently of both heading parsers. Unsupported topics go to `needs_content_review`, and missing source content goes to `needs_context`. This conservative first version may preserve awkward source wording; it is not a substitute for a more sophisticated reviewed language generator. It does not promise ranking or click-through improvements.

History can include page-filtered CSV query exports:

```
python tools/seo/search_metadata/main.py import-csv --engine bing --start 2026-08-03 --end 2026-11-02 --page-url https://manualsdump.com/en/manuals/hp-m1005/286733/69 <page-filtered-queries.csv>
```

Overlapping aggregate windows and daily observations are not added together. For a page/engine, the newer non-overlapping windows are selected, and excluded overlaps are recorded. This can omit part of an older aggregate period rather than inventing daily figures. API daily collection avoids that ambiguity.

After generation the SQLite `proposals` table retains query evidence, decisions and rejected overlaps. Runtime files contain only page metadata. Older evidence cannot overwrite a newer published record. Use a separate directory for each environment.

## Pilot and verification

The saved Bing page-query exports for HP 286733/69, Zebra 153759/44 and Dell 177860/43 supply 878 query rows. The actual corresponding converted HTML and product identities were read from the isolated test server. Three metadata files were generated locally in `artifacts/search-metadata-pilot/active`; the generation report includes the query and content topic chosen for each page. The Google service account has no visible ManualsDump property; the Bing API key is not configured, so full-history collection has not run.

The site/Razor compilation against the deployed test dependencies succeeded with zero errors and 170 project warnings. The ordinary local project build returned a failure without compiler errors, so it is not claimed as passing. Fourteen pipeline tests passed. Fifteen runtime checks include reading the three Python-generated records in .NET. Real IIS requests on an isolated loopback-only instance verified title, H1 and description on all six regular/AMP pages, plus missing-record fallback and restoration without restart. That instance is stopped after the check. The HTTP evidence is in `artifacts/search-metadata-pilot/isolated-http-check.jsonl`.

An attempted shared-test rollout failed its health check and the site returned to the concurrently deployed `headings1` release. The shared test site is healthy; the SEO pilot is not enabled there. Further shared-test rollout must preserve the newer heading deployment. No production site configuration or release was changed.

```
python -m unittest discover -s tools/seo/search_metadata -p test_*.py
dotnet run --project tools/staging/SearchMetadataChecks/SearchMetadataChecks.csproj -c Release
```

API sources: [Google Search Analytics query](https://developers.google.com/webmaster-tools/v1/searchanalytics/query), [Bing GetPageQueryStats](https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.getpagequerystats?view=bing-webmaster-dotnet), [Bing API access](https://learn.microsoft.com/en-us/bingwebmaster/getting-access).
# API history import into research

`tools/seo/search_metadata/import_api_history.py` transfers saved Google and Bing
API query observations from `history.sqlite3` into `research.sqlite3`. It makes no
network calls. Run it in bounded batches with `--limit`; repeating it resumes
without duplicating unchanged windows. Use `--history`, `--db`, `--site`, and
`--evidence-dir` to select paths and the exact GSC property when necessary.

The Google day must have a completed collector checkpoint. Bing data is a retained
snapshot, not a guarantee of historical coverage. Query sums are disclosed subsets,
not page totals. Each provider is now bound to one exact property in its history
database. Mixing properties or silently attaching a property to old unbound API
rows is refused; recollect those rows into a new dedicated history database.
New page identities are held for review unless the same URL and source PDF ID were
already verified in research. Each window has a saved immutable evidence artifact.
No provider credentials are read by this importer. It does not fetch Semrush data,
resolve identities, generate metadata, or publish it.

## Console preparation and Semrush API

The console preparation command connects saved search evidence, Semrush jobs,
and immutable Sol review-and-generation requests:

```powershell
python tools/seo/search_metadata/workflow.py --country US --pages 2 --seeds 2 --related-limit 5
python tools/seo/search_metadata/semrush_workflow.py status
```

This uses saved local evidence only. It creates jobs and writes
`artifacts/search-metadata/workflow/status.json` and `sol-bundles/`.
The generation model runs as user-confirmed Sol 6.1 medium;
this console does not impersonate a model or independently purchase model calls.
Run preparation again after importing provider data or reviewed keywords. The
history importer and planner resume independently. Planning skips already linked
page contexts and can prepare subsequent pages on later invocations.

`semrush_workflow.py` uses the documented v4 keyword-metrics endpoint (20 API units
per request). Optional `--related-limit` uses the documented deprecated v3 related
keywords endpoint, because the current v4 reference only exposes metrics. v3 may
stop working; it is disabled by default. Each expansion reserves 40 units times its
maximum returned rows. Metrics are bound to a requested month; related results
have no verified monthly snapshot. Country metrics are never presented as global
demand; advertiser competition stays separate from organic keyword difficulty.
References: [v4 metrics](https://developer.semrush.com/api/v4/seo/keyword-reports/),
[v3 related keywords](https://developer.semrush.com/api/v3/seo/keyword-reports/),
[v3 column names](https://developer.semrush.com/api/v3/seo/overview/).

After explicit user approval and private credential setup, collection can be run:

```powershell
python tools/seo/search_metadata/semrush_workflow.py collect --approved-api-use --max-units 1000 --limit 8
python tools/seo/search_metadata/semrush_workflow.py candidates --output artifacts/search-metadata/terra-api-candidates.json
python tools/seo/search_metadata/semrush_workflow.py review artifacts/search-metadata/terra-review.json
```

`SEMRUSH_API_KEY` is read only by collection. The budget ceiling is cumulative
across all requests in this research database, including interrupted requests;
rerunning a command does not reset it. Requests are reserved durably before network
access. Failed/uncertain requests retain their reservation and are not retried
automatically, including after a crash. There is no automatic budget release or
reconciliation command: inspect saved proof and the provider billing log before
explicitly implementing any reconciliation. Duplicate keyword/country/month
requests are shared across page contexts. A two-page/two-seed/five-related-row
pilot plans at most 880 units before cache reuse. This is API units, not currency,
and does not prove the user's subscription has API access. Actual entitlement and
live response compatibility remain unverified until an approved pilot succeeds.

In the optional legacy workflow, candidates cannot enter `research_keywords` automatically. A Terra review contains
`model`, `effort`, and a `reviews` array; each review includes `jobId`, `sourcePdfId`,
`page`, `contentSha256`, `keyword`, `decision` (`keep`, `reject`, `no_results`),
`reason`, and verbatim `contentEvidence` for retained keywords. The review importer
checks the actual completed API response, exact page/context link and current
content hash. Unknown metrics stay unknown. An explicit provider no-results report
may be reviewed as `no_results`; an empty/malformed response is a failure. Rejected
candidates remain recorded without unlocking generation. Reviews and raw API
proofs are archived by hash, and the website never reads the job database.

Local pilot on 2026-11-06: preparation completed on the existing research database,
created eight planned requests for two pages (maximum 880 units, zero reserved),
and prepared two Sol bundles from existing previously reviewed browser evidence.
No provider/API-key request or deployment was made by this local pilot.

## Pilot ranking protection

`ranking_policy.py` records actual page-level averages from GSC `Pages.csv`, Bing
page inventories and separate API page aggregates, with provider, URL, exact
reported dates and archived evidence. It never averages the disclosed query rows
to invent a page position. Query reports can omit queries, so their averages are
not a substitute for a page aggregate.

The latest reported window is selected independently for each engine and URL alias.
If any latest known engine/alias position is below 8, the whole page is protected.
If a latest observed window has no page position, the page is held. Google and Bing
positions are not averaged together. The current implementation uses the latest
saved report window; historical evidence is not represented as a fresh live check.
Bing API dates remain returned snapshot labels, with retained-history limitations.

The rule is enforced before Semrush planning, before paid request dispatch (also
for old planned jobs), before generation bundles/queues, and again before exporting
runtime metadata. A previous draft cannot bypass an improved position or a later
identity hold. Rank eligibility is checked separately from metadata semantic input:
a ranking-table backfill alone does not consume another model run.

```powershell
python tools/seo/search_metadata/ranking_policy.py --backfill --output artifacts/search-metadata/workflow/ranking-audit.json
python tools/seo/search_metadata/export_runtime.py --directory artifacts/search-metadata/new-runtime-candidate
```

Backfill uses already archived provider exports and makes no network calls. Runtime
export always requires a new snapshot directory, selects the latest version of each
page, verifies current content/evidence and records exported/held pages with their
ranking decisions. It does not change website configuration or deploy anything.

On 2026-11-06, backfill processed 5,830 saved page reports. Among 58 researched pages,
48 were protected by a position below 8 and ten passed the ranking rule. The first
local position-8 runtime snapshot contained one fresh validated page; 46 other
existing drafts were held (39 ranking protection, six changed research, one needing
review). These are pilot records, not a claim about all site pages or current live
rankings. Production and the shared test site were not changed.
