# Document the GSC ownership boundary

## Why

Some consumers now run GSC from an external artifact, while others still use the Krot package. Krot documentation must not imply that its GSC copy runs for every consumer or that every writer has migrated. Changes to the shared schema also need an explicit compatibility warning.

## What changes

- Document the external GSC runtime boundary and distinguish it from Krot's remaining crawler/ranges runtime
- Warn against changing or deleting the Krot GSC copy and shared schema without checking consumers and coordinating compatibility
