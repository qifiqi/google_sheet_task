# Vue 前端 Composables 文档

> 本文档描述 `frontend/src/composables/` 下所有组合式函数的 API 和使用方式。

## 总览

| Composable | 文件 | 用途 |
|------------|------|------|
| useAuth | `useAuth.js` | JWT 认证状态管理 |
| useNavigation | `useNavigation.js` | 侧边栏导航数据 |
| usePolling | `usePolling.js` | 通用轮询 |
| useResponsive | `useResponsive.js` | 响应式断点检测 |
| useTheme | `useTheme.js` | 主题切换 |
| useChartJs | `useChartJs.js` | Chart.js 懒加载 |
| useDebounce | `useDebounce.js` | 防抖工具 |

---

## usePolling

通用轮询 composable，自动处理 `onMounted` / `onUnmounted` 生命周期，支持页面可见性感知。

```js
import { usePolling } from '@/composables/usePolling'

// 基本用法 — 自动在 onMounted 时启动，onUnmounted 时停止
usePolling(loadData, { interval: 30000 })

// 带条件控制
const { start, stop, tick } = usePolling(loadData, {
  interval: 5000,
  immediate: true,       // 挂载时立即执行一次（默认 true）
  isActive: () => true,  // 返回 false 时跳过本次 tick
})
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| task | Function | **必填** | 轮询执行的异步函数 |
| options.interval | number | `30000` | 轮询间隔 (ms) |
| options.immediate | boolean | `true` | 挂载时是否立即执行 |
| options.isActive | Function | `() => true` | 是否激活判断 |

| 返回值 | 说明 |
|--------|------|
| start() | 手动启动轮询 |
| stop() | 手动停止轮询 |
| tick() | 手动触发一次 |

**注意事项：**
- 已内置 `onMounted` / `onUnmounted`，无需额外调用
- 页面隐藏时自动跳过 tick，恢复可见时立即补一次
- 同一时刻只有一个 tick 在执行（防止并发）

---

## useResponsive

响应式断点检测，基于 RAF 节流的 resize 监听。全局单例，多次调用共享同一监听器。

```js
import { useResponsive } from '@/composables/useResponsive'

const {
  isMobile,          // computed<boolean> — width < 768px
  isTablet,          // computed<boolean> — 768px <= width < 1200px
  isDesktop,         // computed<boolean> — width >= 1200px
  componentSize,     // computed<string> — 'small' | 'default'
  dialogWidth,       // computed<string> — '90%' | '600px' | '50%'
  drawerSize,        // computed<string>
  formLabelPosition, // computed<string> — 'top' | 'right'
  formLabelWidth,    // computed<string>
  tablePageSize,     // computed<number>
  headerHeight,      // computed<string>
  sidebarWidth,      // computed<string>
} = useResponsive()
```

**典型用法：**
```vue
<template>
  <el-table v-if="!isMobile" :data="data" />
  <MobileCardList v-else :data="data" />

  <el-dialog :width="dialogWidth" :fullscreen="isMobile" />
  <el-button :size="componentSize" />
</template>
```

---

## useDebounce

防抖工具函数。

```js
import { useDebounce, useDebouncedRef } from '@/composables/useDebounce'

// 函数防抖
const { debounce, cancel } = useDebounce(300)
debounce(() => fetchData())

// 值防抖
const { value, debouncedValue, update } = useDebouncedRef('', 300)
update(newInput) // debouncedValue 在 300ms 后更新
```

| 函数 | 参数 | 说明 |
|------|------|------|
| useDebounce(delay) | delay: number (默认 300) | 返回 `{ debounce, cancel }` |
| useDebouncedRef(initial, delay) | initial: any, delay: number | 返回 `{ value, debouncedValue, update }` |

---

## useAuth

JWT 认证状态管理，模块级单例。

```js
import { useAuth } from '@/composables/useAuth'

const {
  user,              // ref — 当前用户对象
  permissions,       // ref — 权限代码数组
  isLoggedIn,        // computed<boolean>
  login(credentials),
  logout(),
  fetchUser(),
  hasPermission(code),
} = useAuth()
```

**Token 存储：** localStorage `access_token` / `refresh_token`

---

## useNavigation

侧边栏导航数据，从 `/api/meta/nav` 获取并缓存。

```js
import { useNavigation } from '@/composables/useNavigation'

const { navItems, loadNav } = useNavigation()
```

---

## useTheme

主题切换（light/dark），持久化到 localStorage。

```js
import { useTheme } from '@/composables/useTheme'

const { theme, toggleTheme, isDark } = useTheme()
```

---

## useChartJs

Chart.js 4.x CDN 懒加载。

```js
import { useChartJs } from '@/composables/useChartJs'

const { loadChartJs } = useChartJs()

// 使用
const Chart = await loadChartJs()
new Chart(canvas.getContext('2d'), config)
```
