# Collect configured crawler paths

## Why
Zoopark needs distinct daily requested pages and complete short lists for search crawlers. Existing path capture is restricted to AI readers.

## What Changes
- Add an explicit crawl.path_families list for projects that need path coverage
- Reuse the existing post-classification path capture and storage
- Retain ai_paths compatibility and avoid capturing unrelated high-volume families

## Impact
No schema change or automatic historical reclassification. Existing projects retain their current capture behavior unless they opt in.
