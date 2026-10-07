# Tasks

- [x] Ask the first incomplete date in the API client, validated like every other answer
- [x] Decide availability from it in the collection, with the shared and per-day fallbacks
- [x] Cover both with fakes: zero marker, unavailable without request, borrowed and missing boundary
- [x] Update the wiki page, the contract wording, changelog and collection version
- [x] Two independent reviews before push

## Verification

- Live API 2026-10-03, two properties: `firstIncompleteDate` 2026-09-30, last final date
  2026-09-29; a range without rows answers without metadata
- Unit suite without PostgreSQL: 683 passed; the storage tests run in CI
- Codex adversarial review: accepted the refusal stop after a known boundary; declined the
  borrowed-boundary objection — the only days it can falsely zero lie inside `overlap_days`
- Claude review: accepted range check of the boundary, logged boundary refusals, contract
  wording, stronger tests; declined overlap wipe (unchanged from the probe) and request count
