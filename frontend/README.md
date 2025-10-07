# Google Sheet 任务管理系统 - 前端

基于 Vue 3 + Element Plus 的现代化前端界面，采用类似 1Panel 的设计风格。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **Element Plus** - 基于 Vue 3 的组件库
- **Vue Router** - 官方路由管理器
- **Pinia** - 状态管理
- **Vite** - 现代化构建工具
- **Axios** - HTTP 客户端
- **Day.js** - 轻量级日期处理库

## 项目结构

```
frontend/
├── src/
│   ├── components/          # 公共组件
│   ├── layouts/            # 布局组件
│   │   ├── AdminLayout.vue     # 管理面板布局
│   │   └── GoogleSheetLayout.vue # Google Sheet 布局
│   ├── views/              # 页面组件
│   │   ├── admin/              # 管理面板页面
│   │   │   ├── Dashboard.vue       # 仪表盘
│   │   │   ├── Tasks.vue          # 任务管理
│   │   │   ├── Config.vue         # 系统配置
│   │   │   └── Logs.vue           # 系统日志
│   │   └── google-sheet/       # Google Sheet 页面
│   │       ├── Index.vue          # 任务列表
│   │       ├── Create.vue         # 创建任务
│   │       └── Detail.vue         # 任务详情
│   ├── stores/             # 状态管理
│   ├── utils/              # 工具函数
│   ├── styles/             # 样式文件
│   ├── router/             # 路由配置
│   └── main.js             # 入口文件
├── public/                 # 静态资源
├── package.json            # 项目配置
├── vite.config.js          # Vite 配置
└── README.md              # 说明文档
```

## 开发环境设置

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

应用将在 `http://localhost:8080` 启动，并自动代理 API 请求到后端服务器 `http://localhost:5000`。

### 3. 构建生产版本

```bash
npm run build
```

构建产物将输出到 `../static/dist` 目录，可以直接被 Flask 服务器提供静态文件服务。

### 4. 预览生产版本

```bash
npm run preview
```

## 功能特性

### 🎨 设计特色

- **1Panel 风格**：采用类似 1Panel 的现代化设计风格
- **响应式布局**：支持桌面和移动设备
- **深色主题**：支持深色模式切换
- **动画效果**：流畅的页面切换和交互动画

### 📊 管理面板

- **仪表盘**：系统状态总览和快速操作
- **任务管理**：完整的任务生命周期管理
- **系统配置**：灵活的配置管理界面
- **系统日志**：实时日志查看和搜索

### 📋 Google Sheet 管理

- **任务列表**：直观的任务状态展示
- **创建任务**：向导式任务创建流程
- **任务详情**：详细的执行状态和结果展示
- **实时监控**：任务执行过程的实时更新

### 🔧 技术特性

- **组件化开发**：高度模块化的组件架构
- **状态管理**：基于 Pinia 的响应式状态管理
- **类型安全**：完整的 TypeScript 支持（可选）
- **性能优化**：懒加载、代码分割等优化策略

## API 集成

前端通过 Axios 与后端 Flask API 进行通信：

- **任务管理**：`/api/tasks/*`
- **配置管理**：`/api/config/*`
- **日志查询**：`/api/logs/*`
- **实时事件**：Server-Sent Events (SSE)

## 开发指南

### 添加新页面

1. 在 `src/views/` 下创建 Vue 组件
2. 在 `src/router/index.js` 中添加路由配置
3. 更新导航菜单（如需要）

### 添加新功能

1. 在 `src/stores/` 中添加状态管理
2. 在 `src/utils/api.js` 中添加 API 调用
3. 创建相应的页面组件和业务逻辑

### 样式定制

- 全局样式：`src/styles/index.scss`
- 主题变量：CSS 自定义属性
- 组件样式：使用 scoped CSS

## 部署说明

### 开发环境

1. 启动后端服务器（端口 5000）
2. 启动前端开发服务器（端口 8080）
3. 前端会自动代理 API 请求到后端

### 生产环境

1. 构建前端：`npm run build`
2. 构建产物会输出到 `../static/dist`
3. Flask 服务器会自动提供静态文件服务
4. 访问 `http://localhost:5000` 即可使用完整应用

## 浏览器支持

- Chrome >= 87
- Firefox >= 78
- Safari >= 14
- Edge >= 88

## 故障排除

### 常见问题

1. **端口冲突**：修改 `vite.config.js` 中的端口配置
2. **API 请求失败**：检查后端服务器是否正常运行
3. **样式异常**：清除浏览器缓存或重新构建

### 开发工具

- Vue DevTools：浏览器扩展，用于调试 Vue 应用
- Vite DevTools：开发服务器内置的调试工具

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 发起 Pull Request

## 许可证

MIT License
