# Remove the counts job from indexing

## Why
Krot manages machines. Reading how many pages an engine holds is application data collection, and
the application now reads Bing's figures itself. Two readers of one source spend two sets of calls
and keep two histories.

## What changes
Remove the counts unit and timer, `krot_index.counts`, the engines' reading of page figures, their
schedule, timeout, tests and documentation. A run takes the obsolete units and module off the
machine for the projects it declares. Submissions to the engines are unchanged, and their keys stay.

`krot_index.index_count` and its rows stay in each project's database: schema.sql neither creates,
alters nor drops it. The schema version stays 2, so no database migrates and a program installed by
another project's older run still accepts it. Yandex figures stop being collected; accepted by the
owner.
