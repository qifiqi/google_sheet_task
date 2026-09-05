# Google Picker 上传 Google Drive Demo

这是一个独立可运行的小 Flask 示例，用来验证“全局预览页点击按钮，弹出 Google Picker 组件，然后手动选择 Google Drive 文件夹和文件名上传到真实 Google Drive”的交互。

这个 demo 不使用虚假的 Drive 数据。没有完成 Google OAuth 授权时，获取 token、解析路径和上传接口都会返回 `401`。

## 运行步骤

```powershell
cd demos/google_drive_upload_demo
pip install -r requirements.txt
```

1. 在 Google Cloud Console 创建 OAuth Client，类型选择 Web application。
2. 添加回调地址：

```text
http://127.0.0.1:5010/auth/google/callback
```

3. 下载 OAuth 客户端密钥，保存为：

```text
demos/google_drive_upload_demo/client_secret.json
```

4. 启动 Flask：

```powershell
python app.py
```

5. 打开页面：

```text
http://127.0.0.1:5010
```

6. 点击页面里的“授权 Google Drive”，授权成功后回到首页。

## Google Picker 配置

Google Picker 需要额外配置两个环境变量：

```powershell
$env:GOOGLE_PICKER_API_KEY = "你的 Google API Key"
$env:GOOGLE_PICKER_APP_ID = "你的 Google Cloud Project Number"
python app.py
```

`GOOGLE_PICKER_APP_ID` 通常是 Google Cloud 项目的数字 Project Number，不是项目 ID。

## Demo 功能

- 页面展示一个“单产品 / 多产品全局预览”的示例表格
- 点击“上传到 Google Drive”或“Google Picker”会弹出官方 Google Picker 选择器
- 选择器用于挑选真实 Google Drive 文件夹
- 右侧可以手动输入上传文件名
- 上传接口会生成一个示例 `.xlsx` 并上传到选中的 Google Drive 文件夹

## Google Drive 权限

这个 demo 使用：

```text
https://www.googleapis.com/auth/drive
```

这是为了保证 Picker 选到文件夹后，Flask 后端还能解析文件夹路径并上传文件。真实生产环境里可以再评估是否需要更细粒度地收敛权限。

## 真实接口

后端直接调用 Google Drive API：

- `GET /auth/google/token`：给 Google Picker 获取 access token
- `GET /api/drive/folder-path?folder_id=...`：根据 folder id 解析完整路径
- `POST /api/global-preview/upload`：把生成的 `.xlsx` 上传到真实 Google Drive

## 接入现有项目时的映射

这个 demo 对应到现有项目时，大致可以拆成三块：

- 后端 Drive service：复用 `token` 获取、`folder path` 解析、`upload_file` 三个能力
- 后端预览导出：单产品调用现有 `_build_global_preview_workbook(payload)`，多产品也调用相同导出 workbook 构造逻辑
- 前端页面：在 `templates/backtest_training/global_preview.html` 和 `templates/backtest_multi_product/global_preview.html` 加同一个 Google Picker 组件

真实接入时建议不要把 OAuth token 和现有 Google Sheet token 混在一起。Google Sheet 执行 token 有任务占用语义，而 Drive 上传更像用户操作授权，最好单独保存和管理。
