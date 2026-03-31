-- 添加定时任务分布式锁字段
-- 执行时间: 2026-03-31

ALTER TABLE scheduled_tasks
ADD COLUMN is_running BOOLEAN DEFAULT FALSE,
ADD COLUMN running_instance_id VARCHAR(100);

CREATE INDEX idx_scheduled_tasks_is_running ON scheduled_tasks(is_running);

-- 注释
COMMENT ON COLUMN scheduled_tasks.is_running IS '是否正在执行';
COMMENT ON COLUMN scheduled_tasks.running_instance_id IS '执行实例ID';
