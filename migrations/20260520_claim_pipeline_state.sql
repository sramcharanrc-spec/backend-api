ALTER TABLE claims ADD COLUMN IF NOT EXISTS pipeline_state VARCHAR;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS current_stage VARCHAR;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS approval_required BOOLEAN DEFAULT FALSE;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_claims_pipeline_state ON claims (pipeline_state);
CREATE INDEX IF NOT EXISTS idx_claims_current_stage ON claims (current_stage);
