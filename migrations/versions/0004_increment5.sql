CREATE TABLE clock_observation (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 observed_at timestamptz NOT NULL
);
INSERT INTO clock_observation VALUES (true,clock_timestamp());
GRANT SELECT,UPDATE ON clock_observation TO dfs_runtime;
ALTER TABLE entered_revision ALTER COLUMN draft_id DROP NOT NULL;
