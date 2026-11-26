# Restore human-owned GA4 provisioning

## Why

Site launches need one shared, idempotent GA4 registration mechanism again. An explicit
Analytics account must belong to the same human who owns this domain in Search Console;
a technical launching key is not the human owner and no global owner fallback is allowed.

## What changes

- Restore GA4 modules and opt-in site_analytics.ga4 integration
- Require explicit account ID and human owner email; prove the human is a GSC owner and
  Analytics account administrator before any Analytics write
- Reuse explicit property/stream IDs or unique domain/URL matches across every page;
  refuse ambiguity, preserve all existing property settings, create in Europe/Berlin
- Require an explicit reader service account (which may be the launcher), grant Viewer on the property only and
  prove a Data API read; return property, stream and measurement IDs to the consumer
- Keep application persistence, script insertion and production execution with consumers
