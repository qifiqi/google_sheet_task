<template>
  <div class="login-page">
    <header class="login-topbar">
      <div class="login-brand">
        <span class="login-brand__dot" />
        <div>
          <div class="login-brand__title">Task Validation Platform</div>
          <div class="login-brand__subtitle">参数校验与任务控制台</div>
        </div>
      </div>

      <el-button
        class="theme-toggle"
        round
        @click="toggleTheme"
      >
        <el-icon :size="16">
          <Moon v-if="!isDark" />
          <Sunny v-else />
        </el-icon>
        <span class="hide-mobile">切换{{ isDark ? '浅色' : '深色' }}</span>
      </el-button>
    </header>

    <main class="login-main">
      <section class="login-panel">
        <p class="login-eyebrow">Workspace Access</p>
        <h1 class="login-title">登录系统</h1>
        <p class="login-desc">
          使用现有账号进入任务列表、回测结果、系统配置与模板管理页面。
        </p>

        <el-alert
          v-if="errorMsg"
          :title="errorMsg"
          type="error"
          show-icon
          closable
          class="mb-4"
          @close="errorMsg = ''"
        />

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              autocomplete="username"
              size="large"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
              size="large"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              class="login-submit"
              :loading="loading"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>

        <footer class="login-footer">
          <el-tag size="small" round effect="plain">JWT 登录</el-tag>
          <el-tag size="small" round effect="plain">模板页权限控制</el-tag>
          <el-tag size="small" round effect="plain">动态菜单同步</el-tag>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAuth } from '@/composables/useAuth'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const route = useRoute()
const { login } = useAuth()
const { isDark, toggleTheme } = useTheme()

const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''

  try {
    await login(form.username, form.password)
    const nextUrl = route.query.next || '/task/list'
    router.push(nextUrl)
  } catch (err) {
    errorMsg.value = err?.response?.data?.error || err?.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.14), transparent 22%),
    radial-gradient(circle at bottom right, rgba(245, 158, 11, 0.14), transparent 22%),
    var(--app-bg);
}

html.dark .login-page,
[data-theme="dark"] .login-page {
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.22), transparent 24%),
    radial-gradient(circle at bottom right, rgba(245, 158, 11, 0.18), transparent 24%),
    #020617;
}

.login-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 36px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 14px;

  &__dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: linear-gradient(135deg, #2563eb 0%, #f59e0b 100%);
    box-shadow: 0 0 0 8px rgba(37, 99, 235, 0.12);
  }

  &__title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--app-text);
  }

  &__subtitle {
    font-size: 13px;
    color: var(--app-text-muted);
  }
}

.theme-toggle {
  .el-icon { margin-right: 4px; }
}

.login-main {
  display: flex;
  justify-content: center;
}

.login-panel {
  width: min(460px, 100%);
  padding: 32px;
  border: 1px solid var(--app-border);
  border-radius: 28px;
  background: var(--app-surface);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
}

html.dark .login-panel,
[data-theme="dark"] .login-panel {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(15, 23, 42, 0.88);
  box-shadow: 0 24px 70px rgba(2, 6, 23, 0.46);
}

.login-eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.login-title {
  margin: 0;
  font-size: 38px;
  line-height: 1.04;
  color: var(--app-text);
}

.login-desc {
  margin: 12px 0 24px;
  line-height: 1.7;
  color: var(--app-text-muted);
}

.login-submit {
  width: 100%;
  min-height: 48px;
  border-radius: 14px !important;
  font-weight: 600;
}

.login-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

:deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--app-text);
}

:deep(.el-input__wrapper) {
  border-radius: 12px !important;
  min-height: 44px;
}

@media (max-width: 640px) {
  .login-page { padding: 14px; }
  .login-topbar { margin-bottom: 18px; }
  .login-panel { padding: 22px; border-radius: 22px; }
  .login-title { font-size: 32px; }
}
</style>
