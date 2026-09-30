-- The krot_index schema in a project's database: what krot-index sent and heard.
--
-- Applied by the indexing role, never by the program: a program that created its
-- own schema on a database that had been recreated would forget everything it
-- sent and spend the next fortnight's allowance on repeats, green. The program
-- only checks that this is here and at the version it was written for.
--
-- The shape repeats an earlier PHP implementation's site_page_index and site_index_run column for
-- column, so moving its history over is one INSERT ... SELECT in the same
-- database.
--
-- Idempotent: the role runs it on every pass.

CREATE TABLE IF NOT EXISTS krot_index.page_index (
    site         varchar(255)  NOT NULL,
    engine       varchar(16)   NOT NULL,
    url          varchar(2048) NOT NULL,
    -- indexed / known / unknown. unasked and throttled are never written.
    state        varchar(16)   NOT NULL,
    asked_at     timestamptz   NOT NULL DEFAULT now(),
    -- What we did, apart from what the engine said: accepted is not indexed.
    submitted_at timestamptz,
    PRIMARY KEY (site, engine, url)
);

CREATE INDEX IF NOT EXISTS page_index_site_engine_state ON krot_index.page_index (site, engine, state);

CREATE TABLE IF NOT EXISTS krot_index.index_run (
    site      varchar(255) NOT NULL,
    engine    varchar(16)  NOT NULL,
    -- The machine's day: nobody but this machine measured the night.
    day       date         NOT NULL,
    -- The site's share when the engine named its allowance, else null.
    allowance integer,
    -- The share planned against a guess when it did not, else null.
    floor     integer,
    attempted integer      NOT NULL DEFAULT 0,
    accepted  integer      NOT NULL DEFAULT 0,
    -- Null, not zero, where the site could not be read.
    held      integer,
    waiting   integer,
    -- quota / throttle / ownership / unreadable, null where nothing stopped it.
    refusal   varchar(16),
    ran_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (site, engine, day)
);

CREATE INDEX IF NOT EXISTS index_run_day ON krot_index.index_run (day);

CREATE TABLE IF NOT EXISTS krot_index.schema_version (
    version integer NOT NULL
);

-- One row, whatever it held before: this file IS version 1. In one transaction,
-- because the role reapplies this on every pass and a timer starting between the
-- two statements would find no version and go red over a healthy database.
BEGIN;
DELETE FROM krot_index.schema_version;
INSERT INTO krot_index.schema_version (version) VALUES (1);
COMMIT;
