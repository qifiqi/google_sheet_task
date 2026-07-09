-- C3 XPL async analysis schema patch for PostgreSQL.
-- Run this before starting scripts/run_xpl_analysis_worker.py on an existing production database.

BEGIN;

ALTER TABLE task_results
    ADD COLUMN IF NOT EXISTS return_series_id INTEGER;

CREATE INDEX IF NOT EXISTS ix_task_results_return_series_id
    ON task_results (return_series_id);

ALTER TABLE task_results_return
    ADD COLUMN IF NOT EXISTS returns_json TEXT;

CREATE TABLE IF NOT EXISTS task_result_summary_index (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL,
    task_result_id INTEGER NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    task_name VARCHAR(255),
    stock_code VARCHAR(64),
    stock_name VARCHAR(255),
    model_key VARCHAR(255) NOT NULL DEFAULT 'default',
    model_name VARCHAR(255),
    year_label VARCHAR(64),
    period_key VARCHAR(32),
    kline_range VARCHAR(128),
    parameter_summary TEXT,
    best_metric_name VARCHAR(100),
    best_metric_value DOUBLE PRECISION,
    metrics_json TEXT,
    is_best BOOLEAN NOT NULL DEFAULT FALSE,
    result_timestamp TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE task_result_summary_index
    ADD COLUMN IF NOT EXISTS stock_name VARCHAR(255);

ALTER TABLE task_result_summary_index
    ADD COLUMN IF NOT EXISTS period_key VARCHAR(32);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uk_result_summary_result_model'
    ) THEN
        ALTER TABLE task_result_summary_index
            ADD CONSTRAINT uk_result_summary_result_model UNIQUE (task_result_id, model_key);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_result_summary_task_id'
    ) THEN
        ALTER TABLE task_result_summary_index
            ADD CONSTRAINT fk_result_summary_task_id
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_result_summary_task_result_id'
    ) THEN
        ALTER TABLE task_result_summary_index
            ADD CONSTRAINT fk_result_summary_task_result_id
            FOREIGN KEY (task_result_id) REFERENCES task_results(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_task_id
    ON task_result_summary_index (task_id);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_task_result_id
    ON task_result_summary_index (task_result_id);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_task_type
    ON task_result_summary_index (task_type);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_stock_code
    ON task_result_summary_index (stock_code);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_stock_name
    ON task_result_summary_index (stock_name);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_year_label
    ON task_result_summary_index (year_label);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_best_metric_value
    ON task_result_summary_index (best_metric_value);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_is_best
    ON task_result_summary_index (is_best);

CREATE INDEX IF NOT EXISTS ix_task_result_summary_index_result_timestamp
    ON task_result_summary_index (result_timestamp);

CREATE INDEX IF NOT EXISTS idx_result_summary_type_stock_best
    ON task_result_summary_index (task_type, stock_code, is_best);

CREATE INDEX IF NOT EXISTS idx_result_summary_task_best
    ON task_result_summary_index (task_id, is_best);

CREATE INDEX IF NOT EXISTS idx_result_summary_best_metric
    ON task_result_summary_index (best_metric_value);

CREATE INDEX IF NOT EXISTS idx_result_summary_created_at
    ON task_result_summary_index (created_at);

CREATE INDEX IF NOT EXISTS idx_result_summary_period_key
    ON task_result_summary_index (period_key);

CREATE TABLE IF NOT EXISTS xpl_analysis_jobs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL,
    task_result_id INTEGER NOT NULL,
    return_series_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    locked_by VARCHAR(100),
    locked_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uk_xpl_analysis_jobs_task_result_id'
    ) THEN
        ALTER TABLE xpl_analysis_jobs
            ADD CONSTRAINT uk_xpl_analysis_jobs_task_result_id UNIQUE (task_result_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_xpl_jobs_task_id'
    ) THEN
        ALTER TABLE xpl_analysis_jobs
            ADD CONSTRAINT fk_xpl_jobs_task_id
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_xpl_jobs_task_result_id'
    ) THEN
        ALTER TABLE xpl_analysis_jobs
            ADD CONSTRAINT fk_xpl_jobs_task_result_id
            FOREIGN KEY (task_result_id) REFERENCES task_results(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_xpl_jobs_return_series_id'
    ) THEN
ALTER TABLE xpl_analysis_jobs
    ADD CONSTRAINT fk_xpl_jobs_return_series_id
            FOREIGN KEY (return_series_id) REFERENCES task_results_return(id) ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE xpl_analysis_jobs
    ADD COLUMN IF NOT EXISTS load_elapsed_seconds DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS compute_elapsed_seconds DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS save_elapsed_seconds DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS push_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS push_error_message TEXT;

CREATE INDEX IF NOT EXISTS ix_xpl_analysis_jobs_task_id
    ON xpl_analysis_jobs (task_id);

CREATE INDEX IF NOT EXISTS ix_xpl_analysis_jobs_return_series_id
    ON xpl_analysis_jobs (return_series_id);

CREATE INDEX IF NOT EXISTS ix_xpl_analysis_jobs_status
    ON xpl_analysis_jobs (status);

CREATE INDEX IF NOT EXISTS ix_xpl_analysis_jobs_created_at
    ON xpl_analysis_jobs (created_at);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_status_created
    ON xpl_analysis_jobs (status, created_at);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_status_created_id
    ON xpl_analysis_jobs (status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_status_locked_at
    ON xpl_analysis_jobs (status, locked_at);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_claimable_created_id
    ON xpl_analysis_jobs (created_at, id)
    WHERE status IN ('pending', 'retrying');

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_running_locked_at
    ON xpl_analysis_jobs (locked_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_task_status
    ON xpl_analysis_jobs (task_id, status);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_push_status
    ON xpl_analysis_jobs (push_status);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_task_results_return_series_id'
    ) THEN
        ALTER TABLE task_results
            ADD CONSTRAINT fk_task_results_return_series_id
            FOREIGN KEY (return_series_id) REFERENCES task_results_return(id) ON DELETE SET NULL;
    END IF;
END $$;

COMMIT;
