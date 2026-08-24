-- 修复 t_param_task_logs.message 仍为 VARCHAR 导致的 1406 Data too long。
ALTER TABLE t_param_task_logs
    MODIFY COLUMN message TEXT NOT NULL COMMENT '日志内容';

-- 验证字段类型
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 't_param_task_logs'
  AND COLUMN_NAME = 'message';
