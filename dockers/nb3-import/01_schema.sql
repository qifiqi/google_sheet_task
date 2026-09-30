-- Navicat nb3 导出的表结构（20260929135821），由 meta.json DDL 汇总生成
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `t_param_backtest_product_result_cache` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `batch_id` varchar(64) NOT NULL COMMENT '同批创建ID',
  `cache_key` varchar(64) NOT NULL COMMENT '固定产品结果缓存键',
  `result_json` text NOT NULL COMMENT '结果JSON',
  `returns_json` text COMMENT '收益曲线JSON',
  `source_task_id` varchar(36) DEFAULT NULL COMMENT '来源任务ID',
  `source_step_index` int(11) DEFAULT NULL COMMENT '来源步骤序号',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_backtest_product_cache_batch_key` (`batch_id`,`cache_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='多品回测固定产品同批结果缓存表';

CREATE TABLE `t_param_backtest_sheet_run_locks` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `spreadsheet_id` varchar(255) NOT NULL COMMENT 'Google Sheet 表ID',
  `task_id` varchar(36) NOT NULL COMMENT '持锁任务ID',
  `task_type` varchar(50) NOT NULL COMMENT '任务类型',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_backtest_sheet_run_locks_spreadsheet_id` (`spreadsheet_id`) USING BTREE,
  KEY `ix_t_param_backtest_sheet_run_locks_task_id` (`task_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='回测任务 Google Sheet 运行锁表';

CREATE TABLE `t_param_google_sheet` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT '显示名称',
  `spreadsheet_id` varchar(255) NOT NULL COMMENT 'Google Sheet表ID',
  `table_type` varchar(20) NOT NULL COMMENT '表类型：c3/c4/c5/c7/backtest_training',
  `registry_scope` varchar(32) NOT NULL COMMENT '表类型唯一性分组',
  `remark` text COMMENT '备注',
  `is_active` tinyint(1) NOT NULL COMMENT '是否启用',
  `is_in_use` tinyint(1) NOT NULL COMMENT '是否使用中',
  `current_task_id` varchar(36) DEFAULT NULL COMMENT '当前占用任务ID',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_google_sheet_spreadsheet_registry_scope` (`spreadsheet_id`,`registry_scope`) USING BTREE,
  KEY `ix_t_param_google_sheet_current_task_id` (`current_task_id`) USING BTREE,
  KEY `ix_t_param_google_sheet_name` (`name`) USING BTREE,
  KEY `idx_google_sheet_active_in_use` (`is_active`,`is_in_use`) USING BTREE,
  KEY `ix_t_param_google_sheet_spreadsheet_id` (`spreadsheet_id`) USING BTREE,
  KEY `ix_t_param_google_sheet_is_in_use` (`is_in_use`) USING BTREE,
  KEY `ix_t_param_google_sheet_table_type` (`table_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8 COMMENT='Google Sheet 表ID配置表';

CREATE TABLE `t_param_google_sheet_tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(255) NOT NULL COMMENT 'Token展示名称',
  `task_type` varchar(50) NOT NULL COMMENT '适用任务类型',
  `token_file` varchar(500) NOT NULL COMMENT '运行时落地文件路径',
  `token_context` text NOT NULL COMMENT 'Token JSON原文',
  `task_usage_count` int(11) NOT NULL COMMENT '累计使用次数',
  `current_in_use_count` int(11) NOT NULL COMMENT '当前占用次数',
  `max_usage_count` int(11) NOT NULL COMMENT '最大同时占用次数，0表示不限制',
  `is_active` tinyint(1) NOT NULL COMMENT '是否启用',
  `last_used_at` datetime DEFAULT NULL COMMENT '最后使用时间',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `token_file` (`token_file`) USING BTREE,
  KEY `ix_t_param_google_sheet_tokens_name` (`name`) USING BTREE,
  KEY `idx_google_sheet_token_active_usage` (`is_active`,`current_in_use_count`) USING BTREE,
  KEY `ix_t_param_google_sheet_tokens_task_type` (`task_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8 COMMENT='谷歌 Sheet Token 池表';

CREATE TABLE `t_param_navigation_menu_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '菜单ID',
  `key` varchar(100) NOT NULL COMMENT '菜单唯一键',
  `label` varchar(100) NOT NULL COMMENT '菜单名称',
  `path` varchar(255) DEFAULT NULL COMMENT '前端路由路径',
  `permission` varchar(100) DEFAULT NULL COMMENT '访问该菜单所需权限编码',
  `parent_key` varchar(100) DEFAULT NULL COMMENT '父级菜单key，空表示顶级',
  `sort_order` int(11) NOT NULL COMMENT '排序值',
  `is_visible` tinyint(1) NOT NULL COMMENT '是否显示',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `key` (`key`) USING BTREE,
  KEY `ix_t_param_navigation_menu_items_is_visible` (`is_visible`) USING BTREE,
  KEY `idx_navigation_menu_parent_sort` (`parent_key`,`sort_order`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8 COMMENT='侧边栏导航菜单表';

CREATE TABLE `t_param_permission` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '权限ID',
  `name` varchar(100) NOT NULL COMMENT '权限名称，如"创建任务"',
  `code` varchar(100) NOT NULL COMMENT '权限编码，格式为 资源:操作，如 task:create',
  `group` varchar(50) NOT NULL COMMENT '权限分组，如 task/config/admin',
  `description` varchar(200) DEFAULT NULL COMMENT '权限描述',
  `route_path` varchar(200) DEFAULT NULL COMMENT '关联前端路由路径，如 /admin/config，仅供展示',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=50 DEFAULT CHARSET=utf8 COMMENT='权限表';

CREATE TABLE `t_param_role` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '角色ID',
  `name` varchar(50) NOT NULL COMMENT '角色名称',
  `code` varchar(50) NOT NULL COMMENT '角色编码，如 admin/operator',
  `description` varchar(200) DEFAULT NULL COMMENT '角色描述',
  `is_system` tinyint(1) DEFAULT NULL COMMENT '是否系统内置角色（不可删除）',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8 COMMENT='角色表';

CREATE TABLE `t_param_role_permissions` (
  `role_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `t_param_scheduled_tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '定时任务ID',
  `name` varchar(255) NOT NULL COMMENT '任务名称',
  `description` text COMMENT '任务描述',
  `cron_expression` varchar(100) NOT NULL COMMENT 'Cron表达式',
  `task_type` varchar(50) NOT NULL COMMENT '任务类型',
  `task_function` varchar(255) NOT NULL COMMENT '执行函数名',
  `task_params` text COMMENT '任务参数JSON',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '是否启用',
  `last_run_time` datetime DEFAULT NULL COMMENT '上次执行时间',
  `next_run_time` datetime DEFAULT NULL COMMENT '下次执行时间',
  `run_count` int(11) DEFAULT NULL COMMENT '执行次数',
  `is_running` tinyint(1) DEFAULT NULL COMMENT '是否正在执行',
  `running_instance_id` varchar(100) DEFAULT NULL COMMENT '执行实例ID',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_t_param_scheduled_tasks_created_at` (`created_at`) USING BTREE,
  KEY `ix_t_param_scheduled_tasks_is_active` (`is_active`) USING BTREE,
  KEY `ix_t_param_scheduled_tasks_name` (`name`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8 COMMENT='定时任务表';

CREATE TABLE `t_param_stock_metadata` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `stock_code` varchar(64) NOT NULL COMMENT '股票代码',
  `stock_name` varchar(255) NOT NULL COMMENT '股票名称',
  `market_type` varchar(20) NOT NULL COMMENT '业务市场类型 cn/us',
  `exchange_market` varchar(50) DEFAULT NULL COMMENT '交易市场/东方财富 market',
  `security_type_name` varchar(100) DEFAULT NULL COMMENT '证券类型名称',
  `source` varchar(50) DEFAULT NULL COMMENT '数据来源',
  `raw_json` text COMMENT '原始搜索结果 JSON',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_stock_metadata_code_market_type` (`stock_code`,`market_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1506 DEFAULT CHARSET=utf8 COMMENT='股票元数据表';

CREATE TABLE `t_param_system_configs` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `key` varchar(100) NOT NULL COMMENT '配置键',
  `value` text COMMENT '配置值',
  `description` text COMMENT '配置说明',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `key` (`key`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=102 DEFAULT CHARSET=utf8 COMMENT='系统配置表';

CREATE TABLE `t_param_task_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `task_id` varchar(36) NOT NULL COMMENT '关联任务ID',
  `level` varchar(20) DEFAULT NULL COMMENT '日志级别',
  `message` text NOT NULL COMMENT '日志内容',
  `timestamp` datetime DEFAULT NULL COMMENT '日志时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_t_param_task_logs_timestamp` (`timestamp`) USING BTREE,
  KEY `idx_task_logs_task_timestamp` (`task_id`,`timestamp`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2771 DEFAULT CHARSET=utf8 COMMENT='任务日志表';

CREATE TABLE `t_param_task_result_summary_index` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_id` varchar(36) NOT NULL COMMENT '关联任务ID',
  `task_result_id` int(11) NOT NULL COMMENT '关联任务结果ID',
  `task_type` varchar(50) NOT NULL COMMENT '任务类型',
  `task_name` varchar(255) DEFAULT NULL COMMENT '任务名称',
  `stock_code` varchar(64) DEFAULT NULL COMMENT '股票代码/产品代码',
  `stock_name` varchar(255) DEFAULT NULL COMMENT '股票名称/产品名称',
  `market_type` varchar(8) NOT NULL COMMENT '股票市场类型 cn/us',
  `model_key` varchar(255) NOT NULL COMMENT '模型键',
  `model_name` varchar(255) DEFAULT NULL COMMENT '模型名称',
  `year_label` varchar(64) DEFAULT NULL COMMENT '年份或区间标签',
  `period_key` varchar(32) DEFAULT NULL COMMENT '标准化年份/区间筛选键',
  `kline_range` varchar(128) DEFAULT NULL COMMENT 'K线区间',
  `parameter_summary` text COMMENT '参数摘要',
  `best_metric_name` varchar(100) DEFAULT NULL COMMENT '最优指标名称',
  `best_metric_value` float DEFAULT NULL COMMENT '最优指标值',
  `metrics_json` text COMMENT '汇总指标JSON',
  `is_best` tinyint(1) NOT NULL COMMENT '是否当前分组最优',
  `result_timestamp` datetime DEFAULT NULL COMMENT '原始结果时间',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_result_summary_result_model` (`task_result_id`,`model_key`) USING BTREE,
  KEY `idx_result_summary_created_at` (`created_at`) USING BTREE,
  KEY `idx_result_summary_type_market_best` (`task_type`,`market_type`,`is_best`) USING BTREE,
  KEY `idx_result_summary_type_stock_best` (`task_type`,`stock_code`,`is_best`) USING BTREE,
  KEY `ix_t_param_task_result_summary_index_result_timestamp` (`result_timestamp`) USING BTREE,
  KEY `idx_result_summary_best_metric` (`best_metric_value`) USING BTREE,
  KEY `idx_result_summary_period_key` (`period_key`) USING BTREE,
  KEY `idx_result_summary_task_best` (`task_id`,`is_best`) USING BTREE,
  KEY `ix_t_param_task_result_summary_index_is_best` (`is_best`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7437 DEFAULT CHARSET=utf8 COMMENT='任务结果汇总查询索引表';

CREATE TABLE `t_param_task_results` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '结果ID',
  `task_id` varchar(36) NOT NULL COMMENT '关联任务ID',
  `step_index` int(11) NOT NULL COMMENT '步骤序号',
  `parameters` mediumtext COMMENT '参数JSON',
  `result` mediumtext COMMENT '结果JSON',
  `return_series_id` int(11) DEFAULT NULL COMMENT '收益曲线ID',
  `success` tinyint(1) DEFAULT NULL COMMENT '是否成功',
  `error_message` text COMMENT '错误信息',
  `timestamp` datetime DEFAULT NULL COMMENT '结果时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_t_param_task_results_return_series_id` (`return_series_id`) USING BTREE,
  KEY `idx_success_timestamp` (`success`,`timestamp`) USING BTREE,
  KEY `ix_t_param_task_results_timestamp` (`timestamp`) USING BTREE,
  KEY `idx_task_step` (`task_id`,`step_index`) USING BTREE,
  KEY `idx_task_results_task_timestamp` (`task_id`,`timestamp`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4614586 DEFAULT CHARSET=utf8 COMMENT='任务结果表';

CREATE TABLE `t_param_task_results_return` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_id` varchar(36) NOT NULL COMMENT '关联任务ID',
  `stock_code` varchar(20) NOT NULL DEFAULT 'UNKNOWN' COMMENT '股票代码',
  `stock_name` varchar(20) NOT NULL DEFAULT '未知股票' COMMENT '股票名称',
  `start_return_date` date NOT NULL DEFAULT '1970-01-01' COMMENT '策略起始日期',
  `end_return_date` date NOT NULL DEFAULT '1970-01-01' COMMENT '策略结束日期',
  `return_length` int(11) NOT NULL DEFAULT '0' COMMENT '收益列长度',
  `stock_date` text COMMENT '日期',
  `index_return` text COMMENT '指数收益',
  `start_return` text COMMENT '策略起始收益',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_t_param_task_results_return_task_id` (`task_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7418 DEFAULT CHARSET=utf8 COMMENT='任务收益时间序列表';

CREATE TABLE `t_param_task_templates` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '模板ID',
  `name` varchar(255) NOT NULL COMMENT '模板名称',
  `description` text COMMENT '模板描述',
  `config` text COMMENT '模板配置JSON',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8 COMMENT='任务模板表';

CREATE TABLE `t_param_tasks` (
  `id` varchar(36) NOT NULL COMMENT '任务ID',
  `name` varchar(255) NOT NULL COMMENT '任务名称',
  `description` text COMMENT '任务描述',
  `status` varchar(20) DEFAULT NULL COMMENT '任务状态',
  `task_type` varchar(50) DEFAULT NULL COMMENT '任务类型',
  `config` text COMMENT '任务配置JSON',
  `created_by_user_id` int(11) DEFAULT NULL COMMENT '创建人用户ID',
  `start_time` datetime DEFAULT NULL COMMENT '开始时间',
  `end_time` datetime DEFAULT NULL COMMENT '结束时间',
  `current_step` int(11) DEFAULT NULL COMMENT '当前步骤',
  `total_steps` int(11) DEFAULT NULL COMMENT '总步骤数',
  `error_message` text COMMENT '错误信息',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_status_created` (`status`,`created_at`) USING BTREE,
  KEY `ix_t_param_tasks_created_at` (`created_at`) USING BTREE,
  KEY `idx_type_status` (`task_type`,`status`) USING BTREE,
  KEY `ix_t_param_tasks_created_by_user_id` (`created_by_user_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='任务主表';

CREATE TABLE `t_param_user` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` varchar(80) NOT NULL COMMENT '用户名',
  `password_hash` varchar(256) NOT NULL COMMENT '密码哈希',
  `mobile` varchar(32) DEFAULT NULL COMMENT '手机号',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '是否启用',
  `is_alert_oncall` tinyint(1) NOT NULL COMMENT '是否参与告警值班',
  `token_version` int(11) NOT NULL COMMENT 'JWT 会话版本号',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `last_login` datetime DEFAULT NULL COMMENT '最后登录时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `username` (`username`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8 COMMENT='用户表';

CREATE TABLE `t_param_user_roles` (
  `user_id` int(11) NOT NULL,
  `role_id` int(11) NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `t_param_xpl_analysis_jobs` (
  `id` varchar(255) DEFAULT NULL,
  `task_id` varchar(255) DEFAULT NULL,
  `task_result_id` varchar(255) DEFAULT NULL,
  `return_series_id` varchar(255) DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  `attempts` varchar(255) DEFAULT NULL,
  `max_attempts` varchar(255) DEFAULT NULL,
  `locked_by` varchar(255) DEFAULT NULL,
  `locked_at` varchar(255) DEFAULT NULL,
  `started_at` varchar(255) DEFAULT NULL,
  `finished_at` varchar(255) DEFAULT NULL,
  `error_message` varchar(255) DEFAULT NULL,
  `created_at` varchar(255) DEFAULT NULL,
  `updated_at` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

