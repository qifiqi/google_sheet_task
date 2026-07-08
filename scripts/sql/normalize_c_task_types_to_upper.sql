BEGIN;

UPDATE tasks
SET task_type = CASE task_type
    WHEN 'google_sheet_c4' THEN 'google_sheet_C4'
    WHEN 'google_sheet_c5' THEN 'google_sheet_C5'
    WHEN 'google_sheet_c7' THEN 'google_sheet_C7'
    ELSE task_type
END
WHERE task_type IN ('google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7');

UPDATE task_result_summary_index
SET task_type = CASE task_type
    WHEN 'google_sheet_c4' THEN 'google_sheet_C4'
    WHEN 'google_sheet_c5' THEN 'google_sheet_C5'
    WHEN 'google_sheet_c7' THEN 'google_sheet_C7'
    ELSE task_type
END
WHERE task_type IN ('google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7');

UPDATE scheduled_tasks
SET task_type = CASE task_type
    WHEN 'google_sheet_c4' THEN 'google_sheet_C4'
    WHEN 'google_sheet_c5' THEN 'google_sheet_C5'
    WHEN 'google_sheet_c7' THEN 'google_sheet_C7'
    ELSE task_type
END
WHERE task_type IN ('google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7');

UPDATE task_templates
SET config = replace(
    replace(
        replace(
            replace(
                replace(
                    replace(config, '"task_type": "google_sheet_c4"', '"task_type": "google_sheet_C4"'),
                    '"task_type":"google_sheet_c4"', '"task_type":"google_sheet_C4"'
                ),
                '"task_type": "google_sheet_c5"', '"task_type": "google_sheet_C5"'
            ),
            '"task_type":"google_sheet_c5"', '"task_type":"google_sheet_C5"'
        ),
        '"task_type": "google_sheet_c7"', '"task_type": "google_sheet_C7"'
    ),
    '"task_type":"google_sheet_c7"', '"task_type":"google_sheet_C7"'
)
WHERE config LIKE '%google_sheet_c4%'
   OR config LIKE '%google_sheet_c5%'
   OR config LIKE '%google_sheet_c7%';

UPDATE tasks
SET config = replace(
    replace(
        replace(
            replace(
                replace(
                    replace(config, '"task_type": "google_sheet_c4"', '"task_type": "google_sheet_C4"'),
                    '"task_type":"google_sheet_c4"', '"task_type":"google_sheet_C4"'
                ),
                '"task_type": "google_sheet_c5"', '"task_type": "google_sheet_C5"'
            ),
            '"task_type":"google_sheet_c5"', '"task_type":"google_sheet_C5"'
        ),
        '"task_type": "google_sheet_c7"', '"task_type": "google_sheet_C7"'
    ),
    '"task_type":"google_sheet_c7"', '"task_type":"google_sheet_C7"'
)
WHERE config LIKE '%google_sheet_c4%'
   OR config LIKE '%google_sheet_c5%'
   OR config LIKE '%google_sheet_c7%';

UPDATE scheduled_tasks
SET task_params = replace(
    replace(
        replace(
            replace(
                replace(
                    replace(task_params, '"task_type": "google_sheet_c4"', '"task_type": "google_sheet_C4"'),
                    '"task_type":"google_sheet_c4"', '"task_type":"google_sheet_C4"'
                ),
                '"task_type": "google_sheet_c5"', '"task_type": "google_sheet_C5"'
            ),
            '"task_type":"google_sheet_c5"', '"task_type":"google_sheet_C5"'
        ),
        '"task_type": "google_sheet_c7"', '"task_type": "google_sheet_C7"'
    ),
    '"task_type":"google_sheet_c7"', '"task_type":"google_sheet_C7"'
)
WHERE task_params LIKE '%google_sheet_c4%'
   OR task_params LIKE '%google_sheet_c5%'
   OR task_params LIKE '%google_sheet_c7%';

COMMIT;
