# 第三轮分析：Word 上传云端硬盘指定位置 + 回写登记 Sheet（2026-09-17）

> 承接 [README.md](README.md)、[02-第二轮分析.md](02-第二轮分析.md)。只做分析，未实施。
> 需求理解：① Word 报告生成后直接上传到 Google 云端硬盘的指定文件夹（而不是只回传浏览器下载）；② 上传成功后，把文件信息写入一张指定的登记用 Google Sheet。

---

## 一、两个决定方案边界的现状事实

1. **Token 作用域只有 Sheets**：`google_sheet_client.py:29` `SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]`，构造与重连都用它（:55、:503）。token 池里的全部存量凭据**都没有 Drive 权限**——调用任何 Drive API 都会 403。这是整个需求的硬前提：必须重新授权加作用域，或单独一张 Drive 专用凭据。
2. **没有 Drive 客户端依赖**：requirements.txt 只有 google-auth / google-auth-oauthlib / google-auth-httplib2（gspread 6.2.1 的依赖面），没有 `google-api-python-client`；gspread 本身只管 Sheets，不做任意文件上传。仓库内目前零 Drive 代码。
3. **上传挂点现成**：Word 产物本来就在内存里（`export_service.export_backtest_word` 返回 `GeneratedFile(buffer=BytesIO)`，:349-356，缓存命中时直接是缓存 docx 字节），加"上传"只是多消费一次这份数据。
4. **写登记 Sheet 的能力缺口很小**：`google_sheet_client` 有 update_cell/update_jumped_cells/get_last_row 等，但没有 append 封装；gspread 的 `worksheet.append_row/append_rows` 是现成 API，补一个薄封装即可。
5. 导出端点已有限流（10/min，`export_api.py:36-39`），上传端点应沿用同一限流。

---

## 二、"具体位置"的表达：存文件夹 ID，不存路径

- **方案 a（推荐）**：配置存**文件夹 ID**，从文件夹链接直接解析（`https://drive.google.com/drive/folders/<ID>` 末段）。稳定（文件夹改名不失效）、零额外请求。
- 方案 b：配置存路径（如 `回测报告/2026/`），导出时按 `name + mimeType=folder` 查询解析成 ID。直观但多一次 API 调用，且同名文件夹有歧义、路径段每一级都要查。
- 存放位置：SystemConfig（经 `config_manager.set_config`，注意负缓存规则）：
  - `word_drive_folder_id`（默认上传位置）
  - `word_drive_registry_spreadsheet_id` + `word_drive_registry_sheet_name`（登记表位置）
  - 请求级可覆盖（导出弹窗高级项），与无风险利率弹窗的注入方式一致。
- 团队盘（Shared Drive）：如果目标位置在共享团队盘，上传与查询都要带 `supportsAllDrives=true` / `driveId`——配置里加一个 `word_drive_shared_drive_id` 可选项即可。

---

## 三、凭据与作用域（最重要的决策点）

| 方案 | 做法 | 影响 | 评价 |
|---|---|---|---|
| A：现有池加 drive 作用域 | SCOPES 增加 `.../auth/drive`，**全部存量 token 重新走一次 OAuth 授权** | 影响所有任务执行账号；token 更新流程要跑一遍 | 不推荐：为了一个导出功能动整个 token 池 |
| **B：Drive 专用 token（推荐）** | 单独授权一张只有（或含）drive 作用域的 OAuth token，SystemConfig 指定其 token_id 供上传/登记使用；存量 token 不动 | 只多一张凭据的管理 | 改动面最小；上传与登记用同一张 token，天然要求登记表放在该账号可见的文件里 |
| C：`drive.file` 最小作用域 | 只授权 `.../auth/drive.file` | **该作用域只能访问"本应用自己创建的文件"**——写不进任意既有文件夹；除非目标文件夹也由本应用创建一次（首次运行建文件夹并记录其 ID） | 最小权限，但"用户已有文件夹"场景不覆盖；可作为 B 的收紧版 |

红线对齐：凭据仍走 token_context / 密钥服务，不进源码与日志（AGENTS 红线不变）。

---

## 四、上传链路设计

### 4.1 接口形态

**新增独立端点，不动现有流下载**：

```
POST /api/exports/backtest-reports/word/drive
  body = 原报告请求（StrategyBacktestReportSchema 同款）+ 可覆盖项 {drive_folder_id?, filename?}
  行为 = export_service.export_backtest_word(...) 拿到 docx 字节 → 上传 Drive → 写登记行
  返回 = JSON 信封 {file_id, file_url, file_name, registry_written}
```

- 现有 `POST .../word`（文件流下载）原样保留，前端"导出"与"导出到云端硬盘"两个按钮各走各的端点——避免一个端点在"流/JSON"两种响应形态间摇摆。
- 第二轮的 v3/from-data 路径同样可带 drive 选项（bundle 直驱产物上传），属于同一挂点的复用。
- 复用 `GeneratedFile` 的字节与文件名规则；限流沿用 `_export_limit`。

### 4.2 上传实现选型

- **推荐：requests 直发 REST multipart**：`POST https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart`，metadata `{name, parents: [folderId]}` + docx 字节，用 google-auth 凭据（复用或刷新 access token）。约 30~40 行，无新依赖，失败重试沿用 `_retry_network_operation` 的模式。
- 备选：引入 `google-api-python-client`（MediaFileUpload）。能力全但重；当前只有"上传一个文件"一个动作，不值得。
- 同名冲突：允许重名（Drive 本就允许，登记行带时间戳可区分）；不做"按名检索覆盖"（多查询、还有并发竞态）。
- 可选开关：上传时以 `contentType=application/vnd.google-apps.document` 转成在线 Google Doc（可协作查看，但 Word 版式可能变形）。默认存 .docx 原文件，转换作为显式配置项。

### 4.3 触发模式（两档，分期做）

- **P1 手动（推荐先做）**：导出弹窗 / v3 预览页加"导出到云端硬盘"按钮 → 新端点 → 前端展示返回的文件链接。
- **P2 自动（后续）**：任务完成后自动出报告并上传+登记。挂进任务线程必须遵守 AGENTS 网络语义（可恢复错误抛 `RetryableNetworkTaskError`、写 `error_message`），且看门狗重试不能造成重复上传——幂等键用 `task_id + group_key + 日期`。这一档牵动任务系统，建议独立立项。

---

## 五、上传后写登记 Sheet

### 5.1 登记表布局建议（一行 = 一次上传）

| 时间 | 任务ID | 任务名 | 分组/比例 | 模型版本 | 无风险利率 | 文件名 | Drive 链接 | 文件大小 | 触发方式 |
|---|---|---|---|---|---|---|---|---|---|

- 表头首行由实施时一次性手工建好（不在代码里建表，避免权限与格式问题）。
- "具体的 sheet"由 SystemConfig 的 `word_drive_registry_spreadsheet_id + sheet_name` 定位；**登记表必须放在 Drive 专用 token 同账号可见的文件里**（方案 B 下两张凭据分工：上传与登记同用一张 drive token，任务执行用的 sheets token 不参与）。

### 5.2 写入能力与幂等

- `google_sheet_client` 补一个薄封装 `append_rows(rows: list[list])`（gspread `worksheet.append_rows` 现成，带 `_retry_network_operation`），一次 HTTP 写一行/多行；不要用 get_last_row + update_jumped_cells 拼追加（多一次整列读，还有并发错位风险）。
- **幂等键 = Drive file_id**：登记写入前按 file_id 查一次登记表是否已有该行（一次 `get_range` 或一次性全量读缓存），重试不产生重复行。
- **部分失败策略**：上传成功、登记失败 ≠ 回滚上传（文件已在用户盘里）。返回体带 `registry_written: false` + warning 日志，人工可补；自动触发模式下登记失败要写 `error_message`（遵守 AGENTS：任务线程不吞异常）。
- 顺序：先上传拿到 file_id/链接，再写登记行——登记行依赖链接，顺序天然固定。

---

## 六、实施分期

| 期 | 内容 | 前置 |
|---|---|---|
| P0（用户操作） | 确定作用域方案（B 推荐），完成一次带 drive 作用域的 OAuth 授权，把 token 配置进 SystemConfig；建立登记表表头 | — |
| P1 | `word/drive` 上传端点 + requests multipart 上传 + 弹窗/v3 入口 + 返回链接 | P0 |
| P2 | 登记表写入（append_rows 封装 + file_id 幂等 + 部分失败策略） | P1 |
| P3 | 任务完成自动上传+登记（任务线程语义、看门狗幂等） | P1/P2 稳定后独立立项 |

## 七、决策清单

1. 作用域方案选 B（Drive 专用 token，推荐）还是 C（drive.file + 应用自建文件夹）？
2. 登记表字段按第五节布局定稿？登记表放哪个账号/文件？
3. 是否需要"转 Google Docs 在线文档"开关（默认关，存 .docx 原文件）？
4. 手动触发先做，自动触发（任务完成后）是否立项到 P3？
5. 目标位置是否涉及共享团队盘（影响 supportsAllDrives 参数与配置项）？
