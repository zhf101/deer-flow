# nlp2sql Multi-Database Adapter Design

Date: 2026-03-22
Status: Draft approved by user for implementation
Topic: Extend DeerFlow `nlp2sql` from MySQL/PostgreSQL only to multiple SQL databases using per-database adapters

## 1. Goal

Extend `deerflow.nlp2sql` so that it supports these database types:

- `mysql`
- `postgres`
- `oracle`
- `dm`
- `kingbase`
- `gaussdb`
- `opengauss`
- `oceanbase`
- `tidb`
- `polardb`
- `goldendb`

The user explicitly selected the per-database adapter approach. The implementation should preserve the current `nlp2sql` tool contract and keep the existing read-only validation and query flow intact.

## 2. Context

Current state:

- `nlp2sql` only has two Python adapters: MySQL and PostgreSQL.
- The full flow already depends on the adapter protocol:
  - `connect`
  - `disconnect`
  - `execute_query`
  - `explain_query`
  - `get_schema`
  - `get_table_info`
  - `get_enum_values`
  - `get_sample_rows`
- Frontend settings only expose `mysql` and `postgres`.

Reference project:

- `D:\code\universal-db-mcp` already supports a broader database set.
- Its implementation is TypeScript, so logic can be referenced, but the adapters must be implemented natively in Python inside DeerFlow.

## 3. Non-Goals

This change does not include:

- NoSQL support such as MongoDB or Redis
- A SQLAlchemy-based unification layer
- A generic query abstraction beyond SQL
- End-to-end integration tests against live database servers for every database

## 4. Decision

Adopt approach B: per-database adapters.

This means each database family gets its own adapter module and driver handling, even when it is protocol-compatible with MySQL or PostgreSQL.

Reasoning:

- It matches the user's preference.
- It keeps database-specific schema queries, `EXPLAIN` syntax, quoting rules, and driver error handling isolated.
- It reduces the risk of a unified abstraction masking dialect-specific behavior in `get_schema` and `explain_query`.

Tradeoff:

- More files and more duplicated logic than a unified adapter.
- Higher maintenance cost across compatible database families.

## 5. Adapter Architecture

### 5.1 Adapter surface

The existing `DbAdapter` protocol remains unchanged. All new adapters must implement the current interface so that:

- `service.py` stays mostly unchanged
- `tools.py` stays unchanged
- schema search and validation continue to operate on the same schema document shape

### 5.2 Adapter files

Planned adapter modules:

- `adapters/mysql.py`
- `adapters/postgres.py`
- `adapters/oracle.py`
- `adapters/dm.py`
- `adapters/kingbase.py`
- `adapters/gaussdb.py`
- `adapters/opengauss.py`
- `adapters/oceanbase.py`
- `adapters/tidb.py`
- `adapters/polardb.py`
- `adapters/goldendb.py`

Shared helpers may be added for:

- safe identifier validation and quoting
- common schema document assembly
- common error wrapping
- enum parsing

These helpers must remain optional utility code only. They must not turn into a hidden generic adapter layer.

### 5.3 Factory behavior

`adapters/factory.py` will expand to map each `DatabaseType` to one concrete adapter class.

Alias handling:

- `opengauss` is treated as its own declared type in DeerFlow, even if implementation is initially close to `gaussdb`
- factory may still reuse internal helper functions across these adapters, but the public mapping remains explicit

## 6. Database-Specific Implementation Plan

### 6.1 MySQL-compatible databases

Databases:

- `mysql`
- `oceanbase`
- `tidb`
- `polardb`
- `goldendb`

Driver strategy:

- Use `pymysql`

Implementation strategy:

- Keep `mysql.py` as the reference implementation
- Create dedicated adapter modules for each listed type
- Reuse helper logic where practical, but preserve separate classes and explicit factory wiring

Expected differences:

- default ports
- explain behavior differences in some engines
- schema metadata edge cases

Default ports:

- `mysql`: `3306`
- `oceanbase`: `2881`
- `tidb`: `4000`
- `polardb`: `3306`
- `goldendb`: `3306`

### 6.2 PostgreSQL-compatible databases

Databases:

- `postgres`
- `kingbase`
- `gaussdb`
- `opengauss`

Driver strategy:

- Use `psycopg`

Implementation strategy:

- Keep `postgres.py` as the reference implementation
- Add distinct adapter modules for `kingbase`, `gaussdb`, and `opengauss`
- Start with PostgreSQL-compatible system catalogs and adjust when necessary for comments, schemas, and foreign keys

Default ports:

- `postgres`: `5432`
- `kingbase`: `54321`
- `gaussdb`: `8000`
- `opengauss`: `5432`

### 6.3 Oracle

Driver strategy:

- Use `oracledb`

Implementation strategy:

- Build a dedicated `OracleAdapter`
- Support connection string construction from:
  - `host`
  - `port`
  - `database`
  - optional `service_name`
  - optional `sid`
  - optional `oracle_client_path`
- Use Oracle-specific metadata views and Oracle-specific `EXPLAIN` handling

Default port:

- `1521`

### 6.4 DM

Driver strategy:

- Add a dedicated DM Python driver dependency
- The concrete package must be the official or practically installable DM driver supported by the target environment

Implementation strategy:

- Build a dedicated `DMAdapter`
- Prefer Oracle-like metadata structure where valid
- Keep DM-specific connection handling and result normalization isolated from Oracle

Default port:

- `5236`

## 7. Data Model Changes

`DataSourceConfig` will be expanded to support all target databases.

### 7.1 Database type enum

`DatabaseType` will include:

- `MYSQL`
- `POSTGRES`
- `ORACLE`
- `DM`
- `KINGBASE`
- `GAUSSDB`
- `OPENGAUSS`
- `OCEANBASE`
- `TIDB`
- `POLARDB`
- `GOLDENDB`

### 7.2 Additional connection fields

Add optional fields:

- `service_name: str | None = None`
- `sid: str | None = None`
- `oracle_client_path: str | None = None`

These are mainly for Oracle and possibly Oracle-like deployments.

### 7.3 Default port logic

Replace the current two-database default-port rule with an explicit map keyed by `DatabaseType`.

## 8. Frontend Changes

Files impacted:

- `frontend/src/core/nlp2sql/types.ts`
- `frontend/src/components/workspace/settings/nlp2sql-settings-page.tsx`
- i18n locale files

Required changes:

- expand `DatabaseType` union to all supported values
- add new type labels to the selector
- update default port switching logic per selected database type
- expose Oracle-specific fields when `db_type === "oracle"`
- keep common fields for the other databases

UI goal:

- Do not redesign the page
- Preserve the existing settings flow and only extend the form shape

## 9. Validation and Safety

`SqlValidator` remains SQL-based and stays in place.

Requirements:

- keep current single-statement and read-only restrictions
- continue using `sqlglot` dialect names where available
- preserve adapter-backed `EXPLAIN` checks in strict mode

Risk:

- `sqlglot` dialect coverage for some domestic database types is incomplete

Handling:

- compatible databases will use the closest existing dialect name:
  - MySQL family -> `mysql`
  - PostgreSQL family -> `postgres`
  - Oracle -> `oracle`
  - DM -> closest safe fallback if needed

## 10. Dependencies

Backend dependencies will expand beyond the current set.

Existing:

- `pymysql`
- `psycopg[binary]`
- `sqlglot`

To add:

- `oracledb`
- DM Python driver package

Notes:

- Driver import failures must surface as explicit connection/setup errors
- The implementation must not silently degrade support for a configured database type

## 11. Testing Plan

### 11.1 Backend unit tests

Add or expand tests for:

- factory mapping for all supported database types
- default port assignment for each type
- adapter connection error wrapping
- Oracle optional field validation
- schema behavior for PostgreSQL-compatible and MySQL-compatible families
- driver-missing failure paths for Oracle and DM

### 11.2 Frontend tests

Add coverage for:

- expanded type unions
- database type selector behavior
- per-type default port updates
- Oracle-specific field rendering

### 11.3 Verification commands

Before completion, run targeted verification at minimum:

- backend adapter and service tests
- frontend typecheck or targeted test coverage if available

## 12. Risks

### 12.1 Driver availability

Oracle and DM support depends on Python driver availability in the local environment.

Mitigation:

- add dependency declarations
- fail clearly when import or connection initialization fails

### 12.2 Catalog differences

Even protocol-compatible databases may not expose metadata exactly like MySQL/PostgreSQL.

Mitigation:

- keep dedicated adapters
- start from the closest compatible implementation
- adjust per database instead of forcing one generic reflection path

### 12.3 Explain-plan differences

Strict validation depends on `explain_query`, which is highly dialect-specific.

Mitigation:

- implement per-database explain logic
- keep explain parsing narrow and defensive

## 13. Implementation Sequence

1. Expand config and database types
2. Expand factory mapping
3. Add Oracle and DM adapters
4. Add the remaining MySQL-compatible adapters
5. Add the remaining PostgreSQL-compatible adapters
6. Update frontend settings and types
7. Add tests
8. Run verification

## 14. Success Criteria

This design is considered implemented successfully when:

- DeerFlow can create and instantiate adapters for all requested database types
- the frontend can configure each supported type
- `nlp2sql` keeps the existing tool contract
- strict validation still uses adapter-specific `EXPLAIN`
- no existing MySQL/PostgreSQL behavior regresses in current tests
