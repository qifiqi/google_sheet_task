-- 线上重复结果删除 SQL（2026-10-27，按 task id 执行）
-- 背景：2026-10-24 测试库→线上同步后数据回灌，以下 42 个任务在 t_param_task_results
-- 每条结果出现两份完全相同行（同 step_index + stock_code + kline_key 且 result 逐字节一致）。
-- 保留规则：重复组合保留被 t_param_task_result_kline_links 引用的正本，删未被引用副本。
-- 测试库（PG）已按同一规则清理 20347 行并校验通过（重复清零、kline_links 无悬空）。
--
-- 用法：在一条连接内按顺序执行；第 3 节的 deleted_rows 必须等于第 2 节 backup_rows
-- 且与下方各任务预期行数合计（20347，线上略有出入属正常）相符，否则 ROLLBACK。

-- 参与清理的任务及预期删除行数（测试库实测基准）：
--   2b894fca-be31-45c0-b980-c67abc28b2ef  C1.1.0-叶总-经典-8只-1                800
--   e7433ad3-398e-4eb1-a4f1-a689f5ffea29  C1.1.0-叶总-经典-8只-2                800
--   37f73ec9-234c-4729-a102-d549c4a0a49f  C1.1.0-股票池1                       2367
--   b45e9d39-5f96-44f0-9b84-ab5821f12c2f  C1.1.0-股票池-A股                    1600
--   4f49beea-a76c-4992-bcce-fb7b91f6eb1f  C7.0.2-8ETF-2                        4800
--   80a4ed97-8772-43d3-8695-e160c8b371a0  C7.0.2-8ETF-3                        4800
--   51840e3d-2e62-4381-ac22-94b9a854a4db  C7.0.2-8ETF-1                        3182
--   cf3b48a7-1a28-43f8-ac06-01ba8f549bf6  C7.0.2-叶总-经典ETF8只                1600
--   83c8c6b9-ff81-471c-bfd1-464ff6d0dfad  C7.0.3-XRT                             30
--   30faf741-e807-4e5f-969a-981775439aea  Google Sheet 任务 - 2026/10/21 19:13:53   7
--   01619972-0a32-4c9f-93df-802c0c04ba42  Google Sheet 任务 - 2026/10/21 18:28:00   1
--   6bdda6b6-8983-4f20-9f7a-8070513a0e91  C7.0.3 A股 滚动周末12只 …10231816      12
--   b9b4696a-4726-4a89-bd5e-df596aa793a2  C7.0.3 A股 滚动周末12只 …10241148      12
--   ef158790-2354-490a-a75f-8b5bf2d9a9db  C7.0.3 A股 滚动周末12只 …10231909      12
--   a541f24e-e371-4f1d-a927-6b8d38c82c9c  C7.0.3 A股 滚动周末12只 …10241117      12
--   71bf7786-4c84-4b7b-be4c-8a8f82d91424  C7.0.3 A股 滚动周末12只 …10241044      12
--   27554b76-056c-486b-b1ca-5b875cd3b0ce  C7.0.3 A股 滚动周末12只 …10241128      12
--   ff044a90-aedf-4b66-bbe0-ae8bf9722eee  C7.0.3 A股 滚动周末12只 …10241338      12
--   010f9783-3df4-4a8a-8d98-9d2a3bd6e805  C7.0.3 A股 滚动周末12只 …10241247      12
--   ef9e0d72-7198-4812-87dd-2aa26315752e  C7.0.3 A股 滚动周末12只 …10231826      12
--   6df5fa97-1c04-4c5e-bd81-41a3d32ce22d  C7.0.3 A股 滚动周末12只 …10241054      12
--   616d9189-3453-47bb-8f2f-d2a11e043dff  C7.0.3 A股 滚动周末12只 …10241106      12
--   9bb1b3f0-3d7a-44bb-9546-68d2a391a956  C7.0.3 A股 滚动周末12只 …10231805      12
--   6383b1cf-9739-4b62-a1f4-88b0c2539451  C7.0.3 A股 滚动周末12只 …10241208      12
--   9dd2882f-4964-48d8-9dfe-e02ef63781f4  C7.0.3 A股 滚动周末12只 …10241228      12
--   a968b643-b8bc-4895-8695-89bf729da21e  C7.0.3 A股 滚动周末12只 …10241218      12
--   fb6f7e59-29da-4d53-aa00-a30506a6ddc7  C7.0.3 A股 滚动周末12只 …10241350      12
--   998b10ec-78de-4320-a707-a0dede6ea6e4  C7.0.3 A股 滚动周末12只 …10241257      12
--   9dfa8088-81f7-4202-9d2d-755f8d98d9d1  C7.0.3 A股 滚动周末12只 …10241138      12
--   35c0bbb5-77a5-4658-b06e-489d3f01522b  C7.0.3 A股 滚动周末12只 …10231858      12
--   1f1c290b-d08c-4c26-ad33-9ffabbb98452  C7.0.3 A股 滚动周末12只 …10231915      12
--   de0e0486-f423-4454-9582-b57f456d0f5e  C7.0.3 A股 滚动周末12只 …10241319      12
--   20a8bb0f-f0a4-4124-ba56-544681f5069b  C7.0.3 A股 滚动周末12只 …10241157      12
--   684cb990-23c3-4c61-9af9-7ce90e390aeb  C7.0.3 A股 滚动周末12只 …10231837      12
--   9c57805b-4d39-43fd-88c3-89186426ef96  C7.0.3 A股 滚动周末12只 …10231846      12
--   9e702fed-c5e8-4a8a-8320-a8246a813a11  C7.0.3 A股 滚动周末12只 …10241238      12
--   5a6d8321-61ca-464c-b7f5-83761184155a  C7.0.3 A股 滚动周末12只 …10241307      12
--   1e7f875e-b0e3-4f55-b84b-a4e893a9a37b  C7.0.3 A股 滚动周末12只 …10241036      12
--   9c4ad81b-a552-4c3a-b4e1-fa88c97ba482  C7.0.3 A股 滚动周末12只 …10241329      12
--   e0d600bb-40f3-4e6a-8704-b889f46be54d  百济神州-思源电气-恒立液压等8只(多品)     8
--   19d4d483-64c6-4fbc-94ec-108d0ad2ec2f  百济神州-思源电气-恒立液压等8只(多品)     8
--   091b453b-4c1b-4f7a-96c3-7d55ef4b36ad  台积电-南方铜业-英伟达等(多品)           8

-- ============ 1. 删除前核数（每任务 total - distinct_combo = 上表预期行数） ============
-- 注意：COUNT(DISTINCT a, b, c) 是 MySQL 多参数去重计数写法，不能用行构造器 COUNT(DISTINCT (a,b,c))
SELECT r.task_id,
       COUNT(*) AS total,
       COUNT(DISTINCT r.step_index,
             JSON_UNQUOTE(JSON_EXTRACT(r.parameters, '$.stock_code')),
             JSON_UNQUOTE(JSON_EXTRACT(r.parameters, '$.kline_key'))) AS distinct_combo
FROM t_param_task_results r
WHERE r.task_id IN (
  '2b894fca-be31-45c0-b980-c67abc28b2ef',
  'e7433ad3-398e-4eb1-a4f1-a689f5ffea29',
  '37f73ec9-234c-4729-a102-d549c4a0a49f',
  'b45e9d39-5f96-44f0-9b84-ab5821f12c2f',
  '4f49beea-a76c-4992-bcce-fb7b91f6eb1f',
  '80a4ed97-8772-43d3-8695-e160c8b371a0',
  '51840e3d-2e62-4381-ac22-94b9a854a4db',
  'cf3b48a7-1a28-43f8-ac06-01ba8f549bf6',
  '83c8c6b9-ff81-471c-bfd1-464ff6d0dfad',
  '30faf741-e807-4e5f-969a-981775439aea',
  '01619972-0a32-4c9f-93df-802c0c04ba42',
  '6bdda6b6-8983-4f20-9f7a-8070513a0e91',
  'b9b4696a-4726-4a89-bd5e-df596aa793a2',
  'ef158790-2354-490a-a75f-8b5bf2d9a9db',
  'a541f24e-e371-4f1d-a927-6b8d38c82c9c',
  '71bf7786-4c84-4b7b-be4c-8a8f82d91424',
  '27554b76-056c-486b-b1ca-5b875cd3b0ce',
  'ff044a90-aedf-4b66-bbe0-ae8bf9722eee',
  '010f9783-3df4-4a8a-8d98-9d2a3bd6e805',
  'ef9e0d72-7198-4812-87dd-2aa26315752e',
  '6df5fa97-1c04-4c5e-bd81-41a3d32ce22d',
  '616d9189-3453-47bb-8f2f-d2a11e043dff',
  '9bb1b3f0-3d7a-44bb-9546-68d2a391a956',
  '6383b1cf-9739-4b62-a1f4-88b0c2539451',
  '9dd2882f-4964-48d8-9dfe-e02ef63781f4',
  'a968b643-b8bc-4895-8695-89bf729da21e',
  'fb6f7e59-29da-4d53-aa00-a30506a6ddc7',
  '998b10ec-78de-4320-a707-a0dede6ea6e4',
  '9dfa8088-81f7-4202-9d2d-755f8d98d9d1',
  '35c0bbb5-77a5-4658-b06e-489d3f01522b',
  '1f1c290b-d08c-4c26-ad33-9ffabbb98452',
  'de0e0486-f423-4454-9582-b57f456d0f5e',
  '20a8bb0f-f0a4-4124-ba56-544681f5069b',
  '684cb990-23c3-4c61-9af9-7ce90e390aeb',
  '9c57805b-4d39-43fd-88c3-89186426ef96',
  '9e702fed-c5e8-4a8a-8320-a8246a813a11',
  '5a6d8321-61ca-464c-b7f5-83761184155a',
  '1e7f875e-b0e3-4f55-b84b-a4e893a9a37b',
  '9c4ad81b-a552-4c3a-b4e1-fa88c97ba482',
  'e0d600bb-40f3-4e6a-8704-b889f46be54d',
  '19d4d483-64c6-4fbc-94ec-108d0ad2ec2f',
  '091b453b-4c1b-4f7a-96c3-7d55ef4b36ad'
)
GROUP BY r.task_id
ORDER BY total DESC;

-- ============ 2. 备份表（同库留底，可回滚） ============
CREATE TABLE IF NOT EXISTS backup_t_param_task_results_dupfix_20261027 AS
SELECT a.*
FROM t_param_task_results a
WHERE a.task_id IN (
  '2b894fca-be31-45c0-b980-c67abc28b2ef',
  'e7433ad3-398e-4eb1-a4f1-a689f5ffea29',
  '37f73ec9-234c-4729-a102-d549c4a0a49f',
  'b45e9d39-5f96-44f0-9b84-ab5821f12c2f',
  '4f49beea-a76c-4992-bcce-fb7b91f6eb1f',
  '80a4ed97-8772-43d3-8695-e160c8b371a0',
  '51840e3d-2e62-4381-ac22-94b9a854a4db',
  'cf3b48a7-1a28-43f8-ac06-01ba8f549bf6',
  '83c8c6b9-ff81-471c-bfd1-464ff6d0dfad',
  '30faf741-e807-4e5f-969a-981775439aea',
  '01619972-0a32-4c9f-93df-802c0c04ba42',
  '6bdda6b6-8983-4f20-9f7a-8070513a0e91',
  'b9b4696a-4726-4a89-bd5e-df596aa793a2',
  'ef158790-2354-490a-a75f-8b5bf2d9a9db',
  'a541f24e-e371-4f1d-a927-6b8d38c82c9c',
  '71bf7786-4c84-4b7b-be4c-8a8f82d91424',
  '27554b76-056c-486b-b1ca-5b875cd3b0ce',
  'ff044a90-aedf-4b66-bbe0-ae8bf9722eee',
  '010f9783-3df4-4a8a-8d98-9d2a3bd6e805',
  'ef9e0d72-7198-4812-87dd-2aa26315752e',
  '6df5fa97-1c04-4c5e-bd81-41a3d32ce22d',
  '616d9189-3453-47bb-8f2f-d2a11e043dff',
  '9bb1b3f0-3d7a-44bb-9546-68d2a391a956',
  '6383b1cf-9739-4b62-a1f4-88b0c2539451',
  '9dd2882f-4964-48d8-9dfe-e02ef63781f4',
  'a968b643-b8bc-4895-8695-89bf729da21e',
  'fb6f7e59-29da-4d53-aa00-a30506a6ddc7',
  '998b10ec-78de-4320-a707-a0dede6ea6e4',
  '9dfa8088-81f7-4202-9d2d-755f8d98d9d1',
  '35c0bbb5-77a5-4658-b06e-489d3f01522b',
  '1f1c290b-d08c-4c26-ad33-9ffabbb98452',
  'de0e0486-f423-4454-9582-b57f456d0f5e',
  '20a8bb0f-f0a4-4124-ba56-544681f5069b',
  '684cb990-23c3-4c61-9af9-7ce90e390aeb',
  '9c57805b-4d39-43fd-88c3-89186426ef96',
  '9e702fed-c5e8-4a8a-8320-a8246a813a11',
  '5a6d8321-61ca-464c-b7f5-83761184155a',
  '1e7f875e-b0e3-4f55-b84b-a4e893a9a37b',
  '9c4ad81b-a552-4c3a-b4e1-fa88c97ba482',
  'e0d600bb-40f3-4e6a-8704-b889f46be54d',
  '19d4d483-64c6-4fbc-94ec-108d0ad2ec2f',
  '091b453b-4c1b-4f7a-96c3-7d55ef4b36ad'
)
  AND a.id NOT IN (SELECT result_id FROM t_param_task_result_kline_links WHERE result_id IS NOT NULL)
  AND EXISTS (
    SELECT 1 FROM t_param_task_results b
    WHERE b.task_id = a.task_id
      AND b.id < a.id
      AND b.step_index = a.step_index
      AND JSON_UNQUOTE(JSON_EXTRACT(b.parameters, '$.stock_code')) = JSON_UNQUOTE(JSON_EXTRACT(a.parameters, '$.stock_code'))
      AND JSON_UNQUOTE(JSON_EXTRACT(b.parameters, '$.kline_key'))  = JSON_UNQUOTE(JSON_EXTRACT(a.parameters, '$.kline_key'))
      AND b.result = a.result
  );

SELECT COUNT(*) AS backup_rows FROM backup_t_param_task_results_dupfix_20261027;
-- backup_rows 应与第 1 节各任务 total - distinct_combo 之和一致

-- ============ 3. 删除（事务内执行） ============
START TRANSACTION;

DELETE r FROM t_param_task_results r
JOIN (
  SELECT a.id
  FROM t_param_task_results a
  JOIN t_param_task_results b
    ON b.task_id = a.task_id
   AND b.id < a.id
   AND b.step_index = a.step_index
   AND JSON_UNQUOTE(JSON_EXTRACT(b.parameters, '$.stock_code')) = JSON_UNQUOTE(JSON_EXTRACT(a.parameters, '$.stock_code'))
   AND JSON_UNQUOTE(JSON_EXTRACT(b.parameters, '$.kline_key'))  = JSON_UNQUOTE(JSON_EXTRACT(a.parameters, '$.kline_key'))
   AND b.result = a.result
  WHERE a.task_id IN (
    '2b894fca-be31-45c0-b980-c67abc28b2ef',
    'e7433ad3-398e-4eb1-a4f1-a689f5ffea29',
    '37f73ec9-234c-4729-a102-d549c4a0a49f',
    'b45e9d39-5f96-44f0-9b84-ab5821f12c2f',
    '4f49beea-a76c-4992-bcce-fb7b91f6eb1f',
    '80a4ed97-8772-43d3-8695-e160c8b371a0',
    '51840e3d-2e62-4381-ac22-94b9a854a4db',
    'cf3b48a7-1a28-43f8-ac06-01ba8f549bf6',
    '83c8c6b9-ff81-471c-bfd1-464ff6d0dfad',
    '30faf741-e807-4e5f-969a-981775439aea',
    '01619972-0a32-4c9f-93df-802c0c04ba42',
    '6bdda6b6-8983-4f20-9f7a-8070513a0e91',
    'b9b4696a-4726-4a89-bd5e-df596aa793a2',
    'ef158790-2354-490a-a75f-8b5bf2d9a9db',
    'a541f24e-e371-4f1d-a927-6b8d38c82c9c',
    '71bf7786-4c84-4b7b-be4c-8a8f82d91424',
    '27554b76-056c-486b-b1ca-5b875cd3b0ce',
    'ff044a90-aedf-4b66-bbe0-ae8bf9722eee',
    '010f9783-3df4-4a8a-8d98-9d2a3bd6e805',
    'ef9e0d72-7198-4812-87dd-2aa26315752e',
    '6df5fa97-1c04-4c5e-bd81-41a3d32ce22d',
    '616d9189-3453-47bb-8f2f-d2a11e043dff',
    '9bb1b3f0-3d7a-44bb-9546-68d2a391a956',
    '6383b1cf-9739-4b62-a1f4-88b0c2539451',
    '9dd2882f-4964-48d8-9dfe-e02ef63781f4',
    'a968b643-b8bc-4895-8695-89bf729da21e',
    'fb6f7e59-29da-4d53-aa00-a30506a6ddc7',
    '998b10ec-78de-4320-a707-a0dede6ea6e4',
    '9dfa8088-81f7-4202-9d2d-755f8d98d9d1',
    '35c0bbb5-77a5-4658-b06e-489d3f01522b',
    '1f1c290b-d08c-4c26-ad33-9ffabbb98452',
    'de0e0486-f423-4454-9582-b57f456d0f5e',
    '20a8bb0f-f0a4-4124-ba56-544681f5069b',
    '684cb990-23c3-4c61-9af9-7ce90e390aeb',
    '9c57805b-4d39-43fd-88c3-89186426ef96',
    '9e702fed-c5e8-4a8a-8320-a8246a813a11',
    '5a6d8321-61ca-464c-b7f5-83761184155a',
    '1e7f875e-b0e3-4f55-b84b-a4e893a9a37b',
    '9c4ad81b-a552-4c3a-b4e1-fa88c97ba482',
    'e0d600bb-40f3-4e6a-8704-b889f46be54d',
    '19d4d483-64c6-4fbc-94ec-108d0ad2ec2f',
    '091b453b-4c1b-4f7a-96c3-7d55ef4b36ad'
  )
    AND a.id NOT IN (SELECT result_id FROM t_param_task_result_kline_links WHERE result_id IS NOT NULL)
) dup ON dup.id = r.id;

SELECT ROW_COUNT() AS deleted_rows;
-- deleted_rows 必须等于第 2 节 backup_rows（测试库基准 20347）

-- ============ 4. 提交或回滚 ============
-- 核对无误：
COMMIT;
-- 任一不符：
-- ROLLBACK;

-- ============ 5. 删除后校验 ============
-- 应返回 0 行（每任务重复清零）
SELECT r.task_id,
       COUNT(*) - COUNT(DISTINCT r.step_index,
             JSON_UNQUOTE(JSON_EXTRACT(r.parameters, '$.stock_code')),
             JSON_UNQUOTE(JSON_EXTRACT(r.parameters, '$.kline_key'))) AS dup
FROM t_param_task_results r
WHERE r.task_id IN (
  '2b894fca-be31-45c0-b980-c67abc28b2ef',
  'e7433ad3-398e-4eb1-a4f1-a689f5ffea29',
  '37f73ec9-234c-4729-a102-d549c4a0a49f',
  'b45e9d39-5f96-44f0-9b84-ab5821f12c2f',
  '4f49beea-a76c-4992-bcce-fb7b91f6eb1f',
  '80a4ed97-8772-43d3-8695-e160c8b371a0',
  '51840e3d-2e62-4381-ac22-94b9a854a4db',
  'cf3b48a7-1a28-43f8-ac06-01ba8f549bf6',
  '83c8c6b9-ff81-471c-bfd1-464ff6d0dfad',
  '30faf741-e807-4e5f-969a-981775439aea',
  '01619972-0a32-4c9f-93df-802c0c04ba42',
  '6bdda6b6-8983-4f20-9f7a-8070513a0e91',
  'b9b4696a-4726-4a89-bd5e-df596aa793a2',
  'ef158790-2354-490a-a75f-8b5bf2d9a9db',
  'a541f24e-e371-4f1d-a927-6b8d38c82c9c',
  '71bf7786-4c84-4b7b-be4c-8a8f82d91424',
  '27554b76-056c-486b-b1ca-5b875cd3b0ce',
  'ff044a90-aedf-4b66-bbe0-ae8bf9722eee',
  '010f9783-3df4-4a8a-8d98-9d2a3bd6e805',
  'ef9e0d72-7198-4812-87dd-2aa26315752e',
  '6df5fa97-1c04-4c5e-bd81-41a3d32ce22d',
  '616d9189-3453-47bb-8f2f-d2a11e043dff',
  '9bb1b3f0-3d7a-44bb-9546-68d2a391a956',
  '6383b1cf-9739-4b62-a1f4-88b0c2539451',
  '9dd2882f-4964-48d8-9dfe-e02ef63781f4',
  'a968b643-b8bc-4895-8695-89bf729da21e',
  'fb6f7e59-29da-4d53-aa00-a30506a6ddc7',
  '998b10ec-78de-4320-a707-a0dede6ea6e4',
  '9dfa8088-81f7-4202-9d2d-755f8d98d9d1',
  '35c0bbb5-77a5-4658-b06e-489d3f01522b',
  '1f1c290b-d08c-4c26-ad33-9ffabbb98452',
  'de0e0486-f423-4454-9582-b57f456d0f5e',
  '20a8bb0f-f0a4-4124-ba56-544681f5069b',
  '684cb990-23c3-4c61-9af9-7ce90e390aeb',
  '9c57805b-4d39-43fd-88c3-89186426ef96',
  '9e702fed-c5e8-4a8a-8320-a8246a813a11',
  '5a6d8321-61ca-464c-b7f5-83761184155a',
  '1e7f875e-b0e3-4f55-b84b-a4e893a9a37b',
  '9c4ad81b-a552-4c3a-b4e1-fa88c97ba482',
  'e0d600bb-40f3-4e6a-8704-b889f46be54d',
  '19d4d483-64c6-4fbc-94ec-108d0ad2ec2f',
  '091b453b-4c1b-4f7a-96c3-7d55ef4b36ad'
)
GROUP BY r.task_id
HAVING dup > 0;

-- kline_links 悬空引用应为 0
SELECT COUNT(*) AS dangling_kline_links
FROM t_param_task_result_kline_links l
WHERE NOT EXISTS (SELECT 1 FROM t_param_task_results r WHERE r.id = l.result_id);

-- 确认无误后清理备份表：
-- DROP TABLE backup_t_param_task_results_dupfix_20261027;
