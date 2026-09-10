CREATE TABLE odds_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 setup_id uuid NOT NULL REFERENCES setup_revision, game_id uuid NOT NULL REFERENCES game,
 parent_id uuid REFERENCES odds_revision, source text NOT NULL, reference text NOT NULL,
 observed_at timestamptz NOT NULL, published_at timestamptz,
 total text NOT NULL, home_spread text NOT NULL, reason text NOT NULL,
 actor uuid NOT NULL REFERENCES owner,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE odds_head (
 workspace_id uuid NOT NULL REFERENCES workspace, game_id uuid NOT NULL REFERENCES game,
 revision_id uuid NOT NULL REFERENCES odds_revision, PRIMARY KEY(workspace_id,game_id)
);
CREATE TABLE entered_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 parent_id uuid REFERENCES entered_revision, draft_id uuid NOT NULL REFERENCES draft_revision,
 setup_id uuid NOT NULL REFERENCES setup_revision, pool_id uuid NOT NULL REFERENCES import_batch,
 actor uuid NOT NULL REFERENCES owner, assignments jsonb NOT NULL,
 attestation text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE workspace ADD COLUMN entered_id uuid REFERENCES entered_revision;
ALTER TABLE workspace ADD COLUMN context_revision integer NOT NULL DEFAULT 0;
ALTER TABLE recommendation_request ADD COLUMN options jsonb NOT NULL DEFAULT '{}';
ALTER TABLE recommendation_request ADD COLUMN context jsonb NOT NULL DEFAULT '{}';
ALTER TABLE recommendation_result ADD COLUMN candidates jsonb NOT NULL DEFAULT '[]';
GRANT SELECT,INSERT ON odds_revision,entered_revision TO dfs_runtime;
GRANT SELECT,INSERT,UPDATE ON odds_head TO dfs_runtime;
