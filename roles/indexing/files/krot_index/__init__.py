"""krot-index: a site's new pages offered to search engines, one engine a night.

Runs on the machine from a timer, one unit per project and engine, and writes
what it did into the `krot_index` schema of the project's own database. Every rule it
follows was paid for first by an earlier PHP implementation — see openspec change
2026-09-29-offer-pages-to-search-engines, design.md, for where each one comes
from.
"""
