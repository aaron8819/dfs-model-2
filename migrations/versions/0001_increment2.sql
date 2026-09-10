CREATE TABLE owner (
 id uuid PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
 UNIQUE(issuer, subject)
);
CREATE TABLE auth_flow (
 token_hash text PRIMARY KEY, state text NOT NULL, nonce text NOT NULL,
 verifier text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE session (
 token_hash text PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner,
 csrf text NOT NULL, expires_at timestamptz NOT NULL, revoked boolean NOT NULL DEFAULT false
);
CREATE TABLE contest (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner,
 yahoo_id text NOT NULL, name text NOT NULL, season text NOT NULL, round text NOT NULL,
 UNIQUE(owner_id, yahoo_id)
);
CREATE TABLE rule_revision (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL REFERENCES contest,
 schema_version integer NOT NULL DEFAULT 1, profile jsonb NOT NULL,
 confirmed_by uuid NOT NULL REFERENCES owner, provenance text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE game (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL REFERENCES contest,
 event_key text NOT NULL, away text NOT NULL, home text NOT NULL,
 UNIQUE(contest_id,event_key), CHECK(away <> home)
);
CREATE TABLE slate (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL UNIQUE REFERENCES contest
);
CREATE TABLE slate_revision (
 id uuid PRIMARY KEY, slate_id uuid NOT NULL REFERENCES slate,
 membership_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(slate_id, membership_hash)
);
CREATE TABLE slate_game (
 slate_revision_id uuid NOT NULL REFERENCES slate_revision, game_id uuid NOT NULL REFERENCES game,
 PRIMARY KEY(slate_revision_id, game_id)
);
CREATE TABLE schedule_revision (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL REFERENCES contest,
 provenance text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE schedule_observation (
 schedule_id uuid NOT NULL REFERENCES schedule_revision, game_id uuid NOT NULL REFERENCES game,
 kickoff timestamptz, PRIMARY KEY(schedule_id, game_id)
);
CREATE TABLE lock_decision (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL REFERENCES contest,
 game_id uuid NOT NULL REFERENCES game, schedule_id uuid NOT NULL REFERENCES schedule_revision,
 previous_id uuid REFERENCES lock_decision, deadline timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE lock_head (
 contest_id uuid NOT NULL REFERENCES contest, game_id uuid NOT NULL REFERENCES game,
 decision_id uuid NOT NULL REFERENCES lock_decision, PRIMARY KEY(contest_id,game_id)
);
CREATE TABLE setup_revision (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL REFERENCES contest,
 rule_id uuid NOT NULL REFERENCES rule_revision, slate_revision_id uuid NOT NULL REFERENCES slate_revision,
 schedule_id uuid NOT NULL REFERENCES schedule_revision, timezone text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE raw_blob (
 sha256 text PRIMARY KEY, bytes bytea NOT NULL, byte_length integer NOT NULL,
 media_type text NOT NULL, CHECK(octet_length(bytes)=byte_length)
);
CREATE TABLE source_capture (
 id uuid PRIMARY KEY, blob_hash text NOT NULL REFERENCES raw_blob,
 filename text NOT NULL, imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 provider_updated_at timestamptz
);
CREATE TABLE import_batch (
 id uuid PRIMARY KEY, setup_id uuid NOT NULL REFERENCES setup_revision,
 capture_id uuid NOT NULL REFERENCES source_capture, parser_version text NOT NULL,
 fingerprint text NOT NULL UNIQUE, revision integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE import_validation (
 batch_id uuid PRIMARY KEY REFERENCES import_batch, summary jsonb NOT NULL,
 errors jsonb NOT NULL, schema_version integer NOT NULL DEFAULT 1
);
CREATE TABLE subject (
 id uuid PRIMARY KEY, provider_key text NOT NULL, identity_signature text NOT NULL,
 UNIQUE(provider_key,identity_signature)
);
CREATE TABLE slate_entry (
 id uuid PRIMARY KEY, slate_id uuid NOT NULL REFERENCES slate,
 yahoo_id text NOT NULL, UNIQUE(slate_id,yahoo_id)
);
CREATE TABLE pool_row (
 id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES import_batch,
 entry_id uuid NOT NULL REFERENCES slate_entry, subject_id uuid NOT NULL REFERENCES subject,
 game_id uuid REFERENCES game, physical_line integer NOT NULL, physical_line_end integer NOT NULL,
 raw jsonb NOT NULL, normalized jsonb NOT NULL, issues jsonb NOT NULL,
 UNIQUE(batch_id,physical_line)
);
CREATE INDEX pool_batch ON pool_row(batch_id);
CREATE TABLE workspace (
 id uuid PRIMARY KEY, contest_id uuid NOT NULL UNIQUE REFERENCES contest,
 setup_id uuid NOT NULL REFERENCES setup_revision, active_pool_id uuid REFERENCES import_batch,
 revision integer NOT NULL DEFAULT 0, draft_id uuid, decision_at timestamptz
);
CREATE TABLE draft_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 parent_id uuid REFERENCES draft_revision, schema_version integer NOT NULL DEFAULT 1,
 operations jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE workspace ADD CONSTRAINT workspace_draft_fk FOREIGN KEY(draft_id) REFERENCES draft_revision;
CREATE TABLE draft_assignment (
 draft_id uuid NOT NULL REFERENCES draft_revision, slot text NOT NULL,
 entry_id uuid NOT NULL REFERENCES slate_entry, subject_id uuid NOT NULL REFERENCES subject,
 source_row_id uuid NOT NULL REFERENCES pool_row,
 PRIMARY KEY(draft_id,slot), UNIQUE(draft_id,entry_id),
 CHECK(slot IN ('QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DEF'))
);
CREATE TABLE command_receipt (
 owner_id uuid NOT NULL REFERENCES owner, key uuid NOT NULL,
 payload_hash text NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(owner_id,key)
);
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO dfs_runtime;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA public TO dfs_runtime;
REVOKE ALL ON alembic_version FROM dfs_runtime;
REVOKE INSERT ON owner FROM dfs_runtime;
GRANT UPDATE,DELETE ON auth_flow,session TO dfs_runtime;
GRANT UPDATE ON workspace,lock_head TO dfs_runtime;
-- PostgreSQL requires an UPDATE privilege for SELECT FOR UPDATE on the aggregate.
GRANT UPDATE(name) ON contest TO dfs_runtime;
