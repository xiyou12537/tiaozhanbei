-- SQLite compatibility migration for the unified molecule workflow API.
-- Normal application startup also creates this table through SQLAlchemy metadata.

CREATE TABLE IF NOT EXISTS molecule_workflows (
    workflow_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    idempotency_key VARCHAR(128),
    molecule_name VARCHAR(120) NOT NULL,
    execution_mode VARCHAR(32) NOT NULL DEFAULT 'logical_virtual_qpu',
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    current_stage VARCHAR(64) NOT NULL DEFAULT 'input_validation',
    request_json JSON NOT NULL,
    stages_json JSON NOT NULL,
    result_json JSON,
    error_json JSON,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_molecule_workflows_user
        FOREIGN KEY(user_id) REFERENCES users (id),
    CONSTRAINT uq_molecule_workflow_user_idempotency
        UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_molecule_workflows_user_id
    ON molecule_workflows (user_id);
CREATE INDEX IF NOT EXISTS ix_molecule_workflows_molecule_name
    ON molecule_workflows (molecule_name);
CREATE INDEX IF NOT EXISTS ix_molecule_workflows_status
    ON molecule_workflows (status);
CREATE INDEX IF NOT EXISTS ix_molecule_workflows_created_at
    ON molecule_workflows (created_at);
