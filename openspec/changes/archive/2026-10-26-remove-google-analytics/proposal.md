# Remove Google Analytics from site launches

## Why

The owner has retired Google Analytics for every site. A launch must no longer create GA4 properties, grant Analytics access, return tracking identifiers or require Analytics checks. Existing external accounts and historical data must remain intact.

## What changes

- Remove the GA4 modules, launch defaults, provisioning and preflight checks
- Remove GA4 assertions and fake Analytics APIs from the launch scenario and unit suite
- Keep Umami, Search Console ownership, indexing and Cloudflare behavior
- Document the supported launch contract and release the breaking removal as 12.0.0

## Boundary

The collection serves no live domains and renders no site HTML. Consumer projects remove their existing snippets and verify their domains; they adopt the released collection without cross-project edits here.
