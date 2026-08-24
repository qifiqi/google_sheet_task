-- C7 结果 JSON 可能超过 MySQL TEXT（约 64 KiB）上限。
ALTER TABLE t_param_task_results
    MODIFY COLUMN result MEDIUMTEXT NULL,
    MODIFY COLUMN parameters MEDIUMTEXT NULL,
    MODIFY COLUMN error_message TEXT NULL;

SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 't_param_task_results'
  AND COLUMN_NAME IN ('result', 'parameters', 'error_message');
