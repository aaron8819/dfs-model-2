CREATE TABLE projection_batch (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 setup_id uuid NOT NULL REFERENCES setup_revision, pool_id uuid NOT NULL REFERENCES import_batch,
 fingerprint text NOT NULL UNIQUE, parser_version text NOT NULL,
 declaration jsonb NOT NULL, interpretation jsonb NOT NULL, validation jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE projection_file (
 batch_id uuid NOT NULL REFERENCES projection_batch, position text NOT NULL,
 capture_id uuid NOT NULL REFERENCES source_capture, parsed jsonb NOT NULL,
 PRIMARY KEY(batch_id,position)
);
CREATE TABLE mapping_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 parent_id uuid REFERENCES mapping_revision, items jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE availability_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 parent_id uuid REFERENCES availability_revision, items jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE coverage_report (
 id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES projection_batch,
 mapping_id uuid REFERENCES mapping_revision, availability_id uuid REFERENCES availability_revision,
 report jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE analysis_manifest (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 setup_id uuid NOT NULL REFERENCES setup_revision, pool_id uuid NOT NULL REFERENCES import_batch,
 batch_id uuid NOT NULL REFERENCES projection_batch, mapping_id uuid REFERENCES mapping_revision,
 availability_id uuid REFERENCES availability_revision, coverage_id uuid NOT NULL REFERENCES coverage_report,
 bound_revision integer NOT NULL, policy_version text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE preference_revision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 parent_id uuid REFERENCES preference_revision, items jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE workspace ADD COLUMN mapping_id uuid REFERENCES mapping_revision;
ALTER TABLE workspace ADD COLUMN availability_id uuid REFERENCES availability_revision;
ALTER TABLE workspace ADD COLUMN preference_id uuid REFERENCES preference_revision;
ALTER TABLE workspace ADD COLUMN manifest_id uuid REFERENCES analysis_manifest;
CREATE TABLE recommendation_request (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspace,
 manifest_id uuid NOT NULL REFERENCES analysis_manifest, draft_id uuid REFERENCES draft_revision,
 preference_id uuid REFERENCES preference_revision, bound_revision integer NOT NULL,
 input jsonb NOT NULL, limits jsonb NOT NULL, token uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE recommendation_result (
 request_id uuid PRIMARY KEY REFERENCES recommendation_request,
 status text NOT NULL, result jsonb, validation jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE solve_lease (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 request_id uuid REFERENCES recommendation_request, token uuid,
 expires_at timestamptz
);
INSERT INTO solve_lease(singleton) VALUES (true);
GRANT SELECT,INSERT ON projection_batch,projection_file,mapping_revision,availability_revision,
 coverage_report,analysis_manifest,preference_revision,recommendation_request,recommendation_result TO dfs_runtime;
GRANT SELECT,UPDATE ON solve_lease TO dfs_runtime;
