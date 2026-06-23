# 管理页面分组导航功能

## 功能概述

已为任务管理系统的管理页面添加了分组导航功能，类似现代后台管理系统的可折叠菜单结构。

## 新增功能特性

### 1. 分组结构
- **仪表盘** - 独立顶级菜单
- **任务模块** - 包含任务管理、任务模板、任务结果
- **调度模块** - 包含定时任务
- **系统模块** - 包含系统配置、系统日志
- **业务模块** - 包含Google Sheet等业务功能

### 2. 交互功能
- ✅ **可折叠展开** - 点击分组标题可折叠/展开子菜单
- ✅ **图标动画** - 箭头图标会根据展开状态旋转
- ✅ **状态记忆** - 使用localStorage保存用户的折叠偏好
- ✅ **平滑过渡** - 使用CSS动画实现平滑的展开/折叠效果

### 3. 视觉设计
- **分组标题** - 使用较小的大写字母，灰色显示
- **子菜单缩进** - 子菜单项有适当的左侧缩进
- **图标统一** - 每个菜单项都有对应的Bootstrap图标
- **悬停效果** - 鼠标悬停时的颜色变化

## 技术实现

### CSS样式
```css
.sidebar .nav-group-title {
    color: #6c757d;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.sidebar .nav-group .nav-link {
    padding-left: 2.5rem;
    font-size: 0.9rem;
}
```

### JavaScript功能
- **折叠控制** - 使用Bootstrap的collapse组件
- **图标旋转** - CSS transform实现箭头旋转动画
- **状态持久化** - localStorage保存展开/折叠状态
- **事件监听** - 监听Bootstrap折叠事件

## 分组说明

### 任务模块
- **任务管理** - 创建、执行、监控任务
- **任务模板** - 管理可重用的任务模板
- **任务结果** - 查看任务执行结果

### 调度模块  
- **定时任务** - 管理cron定时任务

### 系统模块
- **系统配置** - 应用配置管理
- **系统日志** - 查看系统运行日志

### 业务模块
- **Google Sheet** - Google表格相关功能

## 使用说明

### 基本操作
1. **展开分组** - 点击分组标题展开子菜单
2. **折叠分组** - 再次点击分组标题折叠子菜单
3. **导航** - 点击子菜单项进入对应页面

### 状态保存
- 用户的折叠偏好会自动保存
- 刷新页面后会恢复之前的展开/折叠状态
- 不同浏览器会有独立的状态记忆

## 自定义扩展

### 添加新分组
1. 在HTML中添加新的nav-group结构
2. 设置唯一的collapse ID
3. 添加对应的CSS样式（如需要）

### 添加新菜单项
1. 在对应分组的collapse容器中添加nav-item
2. 设置正确的路由链接
3. 添加合适的图标

### 示例：添加新分组
```html
<div class="nav-group">
    <div class="nav-group-title" data-bs-toggle="collapse" data-bs-target="#newGroup" aria-expanded="false">
        <span><i class="bi bi-new-icon me-2"></i>新模块</span>
        <i class="bi bi-chevron-down"></i>
    </div>
    <div class="collapse" id="newGroup">
        <div class="nav-item">
            <a class="nav-link" href="/new-feature">
                <i class="bi bi-feature-icon"></i> 新功能
            </a>
        </div>
    </div>
</div>
```

## 兼容性

- **Bootstrap 5** - 使用Bootstrap的collapse组件
- **现代浏览器** - 支持localStorage和CSS transform
- **响应式** - 在移动设备上正常工作

## 优势

1. **更好的组织** - 功能按模块分组，结构清晰
2. **节省空间** - 可折叠设计减少菜单占用空间
3. **用户友好** - 状态记忆提升用户体验
4. **易于扩展** - 模块化设计便于添加新功能
5. **视觉美观** - 现代化的设计风格

## 注意事项

- 确保每个collapse容器有唯一的ID
- 新增菜单项时要设置正确的active状态判断
- 图标使用Bootstrap Icons保持一致性
- 测试在不同屏幕尺寸下的显示效果
