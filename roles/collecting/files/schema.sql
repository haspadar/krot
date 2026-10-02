BEGIN;
-- The krot_collect schema in a project's database: what crawled its sites, day by day.
--
-- Applied by the collecting role, never by the program: a program that created
-- its own schema on a recreated database would start the history over, green.
-- The program only checks that this is here and at the version it was written for.
--
-- Its own schema rather than the indexing one: that program demands exactly one
-- row in krot_index.schema_version, and its role refuses a krot_index schema owned
-- by anybody else. Two programs sharing one schema would break each other.
--
-- Columns, types and keys repeat an earlier PHP implementation's tables exactly
-- (site_crawler_day and the rest, without the site_ prefix), so moving its history
-- over is one INSERT ... SELECT per table in the same database.
--
-- Idempotent: the role runs it on every pass.

-- One row per site, crawler family and day. The family carries its verdict as a
-- suffix: -unverified (named itself, arrived from an address its operator does not
-- publish), -media (fetching photographs), or is `impostor` outright.
CREATE TABLE IF NOT EXISTS krot_collect.crawler_day (
    site     varchar(255) NOT NULL,
    family   varchar(64)  NOT NULL,
    day      date         NOT NULL,
    requests integer      NOT NULL,
    bytes    bigint       NOT NULL,
    -- Status 400 and above.
    errors   integer      NOT NULL,
    PRIMARY KEY (site, family, day)
);

CREATE INDEX IF NOT EXISTS crawler_day_site_day ON krot_collect.crawler_day (site, day);
CREATE INDEX IF NOT EXISTS crawler_day_family ON krot_collect.crawler_day (family, day);

-- The day was read — including a day where only people came, which has this row
-- and no figures. The only thing separating "nobody came" from "nobody looked".
CREATE TABLE IF NOT EXISTS krot_collect.crawler_read (
    site         varchar(255) NOT NULL,
    day          date         NOT NULL,
    collected_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (site, day)
);

-- What each crawler asked for: sections of the site and the class of answer. Summed
-- over sections, equal to crawler_day.requests of the same family and day.
CREATE TABLE IF NOT EXISTS krot_collect.crawler_section (
    site         varchar(255) NOT NULL,
    family       varchar(64)  NOT NULL,
    day          date         NOT NULL,
    section      varchar(16)  NOT NULL,
    status_class smallint     NOT NULL,
    requests     integer      NOT NULL,
    PRIMARY KEY (site, family, day, section, status_class)
);

CREATE INDEX IF NOT EXISTS crawler_section_site_day ON krot_collect.crawler_section (site, day);

-- Everything the site served in a day, people included. requests equals the sum of
-- crawler_day.requests plus human.
CREATE TABLE IF NOT EXISTS krot_collect.request_day (
    site        varchar(255)  NOT NULL,
    day         date          NOT NULL,
    requests    integer       NOT NULL,
    human       integer       NOT NULL,
    -- Status 500 and above, whoever asked.
    errors_5xx  integer       NOT NULL,
    -- Over the lines that carried rt= only: a line without it is not a zero.
    rt_sum      numeric(12,3) NOT NULL,
    rt_count    integer       NOT NULL,
    -- rt strictly above one second.
    slow        integer       NOT NULL,
    robots_5xx  smallint      NOT NULL DEFAULT 0,
    sitemap_5xx smallint      NOT NULL DEFAULT 0,
    home_5xx    smallint      NOT NULL DEFAULT 0,
    PRIMARY KEY (site, day)
);

CREATE INDEX IF NOT EXISTS request_day_day ON krot_collect.request_day (day);

-- The pages AI readers took — only for a project that asks (ai_paths), only bare
-- reader families, the path without its query and cut to 255 bytes.
CREATE TABLE IF NOT EXISTS krot_collect.crawler_path (
    site     varchar(255) NOT NULL,
    family   varchar(64)  NOT NULL,
    day      date         NOT NULL,
    path     varchar(255) NOT NULL,
    requests integer      NOT NULL,
    PRIMARY KEY (site, family, day, path)
);

CREATE INDEX IF NOT EXISTS crawler_path_site_day ON krot_collect.crawler_path (site, day);

-- The ranges crawlers publish, by source; replaced whole per source each night.
CREATE TABLE IF NOT EXISTS krot_collect.bot_range (
    source       varchar(64) NOT NULL,
    family       varchar(64) NOT NULL,
    prefix       varchar(64) NOT NULL,
    published_at timestamptz,
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, family, prefix)
);

CREATE INDEX IF NOT EXISTS bot_range_family ON krot_collect.bot_range (family);

CREATE TABLE IF NOT EXISTS krot_collect.schema_version (
    version integer NOT NULL
);

-- Search reports are independent: adding a dimension changes Google's aggregation.
-- Full source strings survive storage; fixed-width generated keys avoid btree text limits.
-- Fixed UTF8 conversion is deterministic within a database; convert_to itself
-- is STABLE because its destination encoding is normally a caller parameter.
CREATE OR REPLACE FUNCTION krot_collect.text_hash(value text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$ SELECT encode(sha256(convert_to(value, 'UTF8')), 'hex') $$;
CREATE TABLE IF NOT EXISTS krot_collect.search_query (
    site varchar(255) NOT NULL,
    day date NOT NULL,
    search_type text NOT NULL DEFAULT 'web',
    query text NOT NULL,
    country text NOT NULL,
    device text NOT NULL,
    query_hash text GENERATED ALWAYS AS (krot_collect.text_hash(query)) STORED,
    impressions bigint NOT NULL CHECK (impressions >= 0),
    clicks bigint NOT NULL CHECK (clicks >= 0),
    position double precision NOT NULL CHECK (position >= 0 AND position < 'Infinity'::float8),
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site, day, search_type, query_hash, country, device)
);
CREATE INDEX IF NOT EXISTS search_query_day ON krot_collect.search_query (day);
CREATE TABLE IF NOT EXISTS krot_collect.search_page (
    site varchar(255) NOT NULL,
    day date NOT NULL,
    search_type text NOT NULL DEFAULT 'web',
    url text NOT NULL,
    url_hash text GENERATED ALWAYS AS (krot_collect.text_hash(url)) STORED,
    impressions bigint NOT NULL CHECK (impressions >= 0),
    clicks bigint NOT NULL CHECK (clicks >= 0),
    position double precision NOT NULL CHECK (position >= 0 AND position < 'Infinity'::float8),
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site, day, search_type, url_hash)
);
CREATE INDEX IF NOT EXISTS search_page_day ON krot_collect.search_page (day);
CREATE TABLE IF NOT EXISTS krot_collect.search_page_query (
    site varchar(255) NOT NULL,
    day date NOT NULL,
    search_type text NOT NULL DEFAULT 'web',
    url text NOT NULL,
    query text NOT NULL,
    url_hash text GENERATED ALWAYS AS (krot_collect.text_hash(url)) STORED,
    query_hash text GENERATED ALWAYS AS (krot_collect.text_hash(query)) STORED,
    impressions bigint NOT NULL CHECK (impressions >= 0),
    clicks bigint NOT NULL CHECK (clicks >= 0),
    position double precision NOT NULL CHECK (position >= 0 AND position < 'Infinity'::float8),
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site, day, search_type, url_hash, query_hash)
);
CREATE INDEX IF NOT EXISTS search_page_query_day ON krot_collect.search_page_query (day);
CREATE TABLE IF NOT EXISTS krot_collect.search_day (
    site varchar(255) NOT NULL,
    day date NOT NULL,
    search_type text NOT NULL DEFAULT 'web',
    dataset text NOT NULL CHECK (dataset IN ('query', 'page', 'page_query')),
    property text NOT NULL,
    row_count bigint NOT NULL CHECK (row_count >= 0),
    collected_at timestamptz NOT NULL DEFAULT now(),
    pagination_complete boolean,
    coverage_limited boolean NOT NULL DEFAULT true,
    finalized boolean NOT NULL DEFAULT true,
    provenance text NOT NULL DEFAULT 'api' CHECK (provenance IN ('api', 'imported')),
    PRIMARY KEY (site, day, search_type, dataset)
);
CREATE INDEX IF NOT EXISTS search_day_day ON krot_collect.search_day (day);
CREATE TABLE IF NOT EXISTS krot_collect.search_attempt (
    attempt_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    site varchar(255) NOT NULL,
    day date NOT NULL,
    search_type text NOT NULL DEFAULT 'web',
    dataset text NOT NULL CHECK (dataset IN ('query', 'page', 'page_query')),
    property text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'unavailable')),
    row_count bigint,
    error text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS search_attempt_day ON krot_collect.search_attempt (day);

-- Upgrade the version only after every additive table was created successfully.
DELETE FROM krot_collect.schema_version;
INSERT INTO krot_collect.schema_version (version) VALUES (2);
COMMIT;
