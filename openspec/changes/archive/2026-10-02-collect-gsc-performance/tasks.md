# Tasks

- [x] Publish configuration, schema and read-only contract to consumers
- [x] Implement finalized API client and report pagination with bounded retries
- [x] Implement daily backfill, overlap, missing-day repair and freshness checks
- [x] Implement versioned schema upgrade, atomic day/report storage, attempts and exports
- [x] Extend role with opt-in jobs, private credential file and additional readers
- [x] Verify client/orchestration with fakes and storage against PostgreSQL
- [x] Verify role check mode, upgrade, permissions, timers and idempotence with Molecule
- [x] Update wiki, changelog, collection version and generated index
- [x] Complete two independent reviews and resolve findings before push

## Verification

- Full unit suite against PostgreSQL 18: 712 passed, no skipped tests
- Molecule collecting: fresh check, converge, idempotence and verify; no live Google requests
- YAML and Ansible production lint, wiki lint/index and collection build
- Two independent Codex reviews: behavior/integration and adversarial failure/security
- Fixed review findings: persistent repair horizon for failed/imported days; server cursor export
- Production provisioning, live GSC calls and consumer cutover are explicitly deferred
