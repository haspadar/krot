# Remove GSC from collecting

## Why
Search collection belongs to the application owner. Krot keeps crawler infrastructure only.

## What changes
Remove the GSC runtime, export command, configuration and tests from collecting. Only ranges and crawl remain valid jobs. Keep schema version 2 for crawler compatibility; omit search DDL without dropping or modifying existing search tables and their history. Remove obsolete installed runtime files during upgrades.
