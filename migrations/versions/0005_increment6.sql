CREATE TABLE operational_state (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 schema_version text NOT NULL,
 recovery_required boolean NOT NULL DEFAULT false,
 invalid_before timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00Z'
);
INSERT INTO operational_state(singleton,schema_version) VALUES(true,'0005_increment6');
CREATE TABLE operational_event (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 operator text NOT NULL, action text NOT NULL, evidence text NOT NULL
);
GRANT SELECT ON operational_state,operational_event TO dfs_runtime;
