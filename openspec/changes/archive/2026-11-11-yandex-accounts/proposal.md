# Select the existing Yandex account for each site

## Why

Sites may already belong to different Yandex Webmaster accounts. A single project token cannot submit or read all of them. Account selection must use existing ownership without moving sites or reusing one token for every site.

## What changes

- Add optional project `yandex_accounts`, mapping `[a-z0-9]+` account names to OAuth tokens, and optional site `yandex_account`
- Keep `yandex_token` and `KROT_INDEX_YANDEX_TOKEN` for sites without an account; require the default token only while such a Yandex site exists
- Write account tokens only to the private env file as `KROT_INDEX_YANDEX_TOKEN_<UPPERCASE_ACCOUNT>`; keep public JSON free of tokens
- Group both submissions and counts by account, with independent Yandex engines and no fallback to another account when a token is missing
- Apply the existing Bing account validation rules to Yandex, including unused accounts, invalid values and duplicate tokens

## Scope

Only the portable indexing role, CLI, counts, tests and documentation. No ownership changes, consumer modifications or production application.
