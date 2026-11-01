# Six daily guides: 2–7 November 2026

Owner-authorized release prepared on 1 November 2026. English articles; one per day at **09:00 Europe/Kyiv**, equivalent to **07:00 UTC** for all six dates. The timestamp in `content/catalog.json` is authoritative. Existing ten articles remain public.

| Kyiv release | Article / slug | Representative measured query | Market | Semrush monthly volume | KD |
|---|---|---|---|---:|---:|
| 2026-11-02 09:00 | `electrolux-oven-clock` | how to reset clock on electrolux oven | UK | 110 | 9 |
| 2026-11-03 09:00 | `craftsman-garage-door-opener-reset` | how to reset craftsman garage door opener | US | 390 | 0 |
| 2026-11-04 09:00 | `fisher-paykel-dishwasher-not-draining` | fisher paykel dishwasher not draining | US | 110 | 15 |
| 2026-11-05 09:00 | `fisher-paykel-dishdrawer-f1-error` | f1 fault on fisher and paykel dishwasher | AU | 210 | 12 |
| 2026-11-06 09:00 | `aeg-oven-symbols` | aeg oven grill symbol | UK | 260 | 12 |
| 2026-11-07 09:00 | `zanussi-dishwasher-symbols` | zanussi dishwasher symbols | UK | 1,300 | 11 |

## Selection and query coverage

- **Electrolux:** setting/changing/resetting time, a flashing clock and post-power-cut checks share a time-of-day task. Measured UK variants include “how to set the clock on an electrolux oven” (110, KD 15) and “how to set the time on an electrolux oven” (110, KD 13). General heating faults are only a boundary, not a second topic.
- **Craftsman:** distinguish code erasure, remote pairing and keypad settings. “craftsman garage door opener reset” has 390 / KD 17, despite the longer phrase's KD 0; “how to reset craftsman garage door opener 1 2 hp” has 210 / KD 6. The existing troubleshooting article remains the symptom-first destination. A second broad remote-not-working article was excluded to reduce overlap.
- **Fisher & Paykel drainage:** cover “not draining” and drawer variants together. Several drawer variants have US 70 / KD 14; the near-identical “fisher and paykel dishwasher not draining” has 110 / KD 26. A low KD for one wording does not make the entire topic easy.
- **Fisher & Paykel F1:** a distinct flood-warning task. The same representative query has US 110 / KD 12 and AU 210 / KD 12. AU “fisher and paykel dishwasher fault f1” has 50 / KD 11. It is separate from a no-code drainage symptom and does not generalize F1 across all models.
- **AEG:** grill, fan and Competence symbol interpretation are consolidated into one model-aware function guide. “grill symbol aeg oven” has UK 140 / KD 18; “aeg competence oven symbols” 210 / KD 22. No Semrush estimate is invented for the broader title query.
- **Zanussi:** “zanussi dishwasher symbols meaning” has UK 260 / KD 9; reversed wording “dishwasher symbols zanussi” has 1,000 / KD 18. Recorded visible Google samples overlapped at five URLs out of eight/eight. Salt is a supporting indicator explanation, not a claim that a dedicated salt-filling query has the same intent or established metrics.

The figures come from existing Semrush Keyword Magic captures dated 1 November 2026 (`semrush-live-2026-11-01.md`, `semrush-google-reviewed-metrics-2026-11-01.csv`, `aeg-oven-symbols-research-2026-11-01.md` in the earlier local answer-intent research folder). The interface showed metrics updated approximately one month earlier. No fresh Semrush search is claimed for this release. Query variants overlap; do not sum volumes. GSC/Bing source-site impressions are not market volume. Official manufacturer sites and established guides compete for these queries; low organic competition and rankings are not guaranteed.

Manual/PDF-download intent, bare-model pages and the overlapping remote-not-working draft are excluded. Five existing drafts were revised; the Zanussi dishwasher-symbols guide is new. Sources, model boundaries and original conceptual schematics are preserved.

## Release behaviour

The production snapshot contains all sixteen articles. Runtime lookups apply `publishAt <= current UTC time`; articles without a timestamp are immediately public. The same filter governs direct URLs, metadata, home, topics, search, related cards, counts and sitemap. Contextual links to future guides remain readable text until release. Empty topic pages also remain hidden until their first guide is published. Pages are dynamic. HTML uses non-cacheable response headers; the dynamic sitemap has zero cache lifetime and requires revalidation before reuse.

No daily deployment or scheduled job is required. The first request at or after 09:00 Kyiv receives the newly eligible article. An already-open page needs reloading. Search engines discover updates on their own crawl schedule; publication does not guarantee immediate indexing.

Tests cover all six exact boundaries on a persistent repository connection and validate timestamps. HTTP smoke checks both published and scheduled paths, links, indexing and cache headers. Source-based editorial review is not an equipment test or independent engineer certification.
