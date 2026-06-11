BEGIN;

CREATE TABLE IF NOT EXISTS payer_rules (
    id SERIAL PRIMARY KEY,
    payer_name VARCHAR NOT NULL,
    rule_name VARCHAR NOT NULL,
    rule_type VARCHAR NOT NULL,
    condition JSONB DEFAULT '{}'::jsonb,
    action JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_payer_rules_payer_name ON payer_rules (payer_name);
CREATE INDEX IF NOT EXISTS ix_payer_rules_rule_type ON payer_rules (rule_type);
CREATE INDEX IF NOT EXISTS ix_payer_rules_created_at ON payer_rules (created_at);

CREATE TABLE IF NOT EXISTS decision_logs (
    id SERIAL PRIMARY KEY,
    claim_id VARCHAR NOT NULL,
    agent VARCHAR NOT NULL,
    input_payload JSONB DEFAULT '{}'::jsonb,
    rules_evaluated JSONB DEFAULT '[]'::jsonb,
    decision VARCHAR NOT NULL,
    reasoning TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_decision_logs_claim_id ON decision_logs (claim_id);
CREATE INDEX IF NOT EXISTS ix_decision_logs_agent ON decision_logs (agent);
CREATE INDEX IF NOT EXISTS ix_decision_logs_decision ON decision_logs (decision);
CREATE INDEX IF NOT EXISTS ix_decision_logs_timestamp ON decision_logs (timestamp);

CREATE TABLE IF NOT EXISTS claim_metrics (
    id SERIAL PRIMARY KEY,
    claim_id VARCHAR NOT NULL,
    metric_name VARCHAR NOT NULL,
    metric_value DOUBLE PRECISION DEFAULT 0,
    dimensions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_claim_metrics_claim_id ON claim_metrics (claim_id);
CREATE INDEX IF NOT EXISTS ix_claim_metrics_metric_name ON claim_metrics (metric_name);
CREATE INDEX IF NOT EXISTS ix_claim_metrics_created_at ON claim_metrics (created_at);

CREATE TABLE IF NOT EXISTS agent_events (
    id SERIAL PRIMARY KEY,
    claim_id VARCHAR,
    agent VARCHAR NOT NULL,
    stage VARCHAR,
    status VARCHAR NOT NULL,
    progress DOUBLE PRECISION,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration DOUBLE PRECISION,
    input_count INTEGER,
    output_count INTEGER,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_events_claim_id ON agent_events (claim_id);
CREATE INDEX IF NOT EXISTS ix_agent_events_agent ON agent_events (agent);
CREATE INDEX IF NOT EXISTS ix_agent_events_stage ON agent_events (stage);
CREATE INDEX IF NOT EXISTS ix_agent_events_status ON agent_events (status);
CREATE INDEX IF NOT EXISTS ix_agent_events_created_at ON agent_events (created_at);

CREATE TABLE IF NOT EXISTS case_escalations (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    level INTEGER DEFAULT 1,
    from_role VARCHAR,
    to_role VARCHAR NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_case_escalations_case_id ON case_escalations (case_id);
CREATE INDEX IF NOT EXISTS ix_case_escalations_status ON case_escalations (status);
CREATE INDEX IF NOT EXISTS ix_case_escalations_created_at ON case_escalations (created_at);

ALTER TABLE cases ADD COLUMN IF NOT EXISTS assigned_team VARCHAR;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sla_deadline TIMESTAMP;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS next_stage VARCHAR;

UPDATE cases
SET assigned_team = COALESCE(assigned_team, assigned_role),
    sla_deadline = COALESCE(sla_deadline, sla_due_at)
WHERE assigned_team IS NULL OR sla_deadline IS NULL;

ALTER TABLE claims ADD COLUMN IF NOT EXISTS form_type VARCHAR;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS ocr_text TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS extraction_summary JSONB DEFAULT '{}'::jsonb;

COMMIT;
