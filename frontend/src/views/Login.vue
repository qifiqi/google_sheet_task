<template>
  <div class="login-page">
    <header class="login-page__topbar">
      <div class="login-page__brand">
        <span class="login-page__brand-dot" />
        <div>
          <div class="login-page__brand-title">Task Validation Platform</div>
          <div class="login-page__brand-subtitle">参数校验与任务控制台</div>
        </div>
      </div>

      <el-switch
        v-model="switchValue"
        class="login-page__theme-switch"
        :active-action-icon="Moon"
        :inactive-action-icon="Sunny"
        inline-prompt
      />
    </header>

    <main class="login-page__main">
      <section class="login-page__panel">
        <div class="login-page__intro">
          <p class="login-page__eyebrow">Workspace Access</p>
          <h1 class="login-page__title">登录系统</h1>
          <p class="login-page__description">使用现有账号进入任务列表、回测结果和系统配置。</p>
        </div>

        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          label-position="top"
          class="login-form"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model.trim="loginForm.username"
              size="large"
              placeholder="请输入用户名"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="loginForm.password"
              size="large"
              type="password"
              placeholder="请输入密码"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-button
            type="primary"
            size="large"
            class="login-form__submit"
            :loading="loginLoading || ssoLoading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>

        <footer class="login-page__footer">
          <span class="login-page__hint">JWT 登录</span>
          <span class="login-page__hint">模板页权限控制</span>
          <span class="login-page__hint">动态菜单同步</span>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAuth } from '@/composables/useAuth'
import { useTheme } from '@/composables/useTheme'
import { ssoExchange } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const { login, fetchUser, getToken, applyAuthData } = useAuth()
const { switchValue } = useTheme()

const loginLoading = ref(false)
const ssoLoading = ref(false)
const loginFormRef = ref()

const loginForm = reactive({
  username: '',
  password: '',
})

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

// next 仅允许同源相对路径（防开放重定向：/login?next= 是外部可达参数，
// 拒绝 // 开头与 CR/LF，对齐静态版 sanitizeNextUrl）。
function sanitizeNextUrl(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed.startsWith('/') || trimmed.startsWith('//') || /[\r\n]/.test(trimmed)) {
    return null
  }
  return trimmed
}

function resolveNextUrl() {
  // 缺省回退 /admin（SPA 路由表的仪表盘是 /admin，无 /admin/dashboard 路由与兜底路由）
  return sanitizeNextUrl(route.query.next) || '/admin'
}

// 主服务 SSO 换票：/login#sso_token=<主服务Token>。fragment 不发给服务端、
// 不进 Referer，读到后立即 replaceState 清掉；换票失败保留账号密码登录兜底。
function consumeSsoTokenFromHash() {
  const match = window.location.hash.match(/(?:^|#|&)sso_token=([^&]+)/)
  if (!match) return null
  let token = match[1]
  try {
    token = decodeURIComponent(token)
  } catch {
    // 保留原值：主服务侧未编码时仍可透传
  }
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
  return token
}

onMounted(async () => {
  // 对齐静态版 bindLoginPage：本地已有可用会话先复用（fetchUser 内含 401
  // 自动刷新续期），校验失败才降级；之后才用 sso_token 换票。携带 sso_token
  // 一律先换票会在同一浏览器换主服务账号时立即切换身份，故不采用。
  const ssoToken = consumeSsoTokenFromHash()
  if (getToken()) {
    const me = await fetchUser()
    if (me) {
      router.replace(resolveNextUrl())
      return
    }
    // fetchUser 失败时已清本地登录态；无 sso_token 则留在登录页走账密表单
    if (!ssoToken) return
  } else if (!ssoToken) {
    return
  }

  ssoLoading.value = true
  try {
    const data = await ssoExchange(ssoToken)
    applyAuthData(data)
    router.replace(resolveNextUrl())
  } catch (error) {
    ElMessage.error(error.message || '主服务登录失败，请使用账号密码登录')
  } finally {
    ssoLoading.value = false
  }
})

async function handleLogin() {
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loginLoading.value = true
  try {
    await login(loginForm.username, loginForm.password)
    // 支持 ?next= 登录后回跳原页面（仅同源相对路径，见 sanitizeNextUrl）
    router.push(resolveNextUrl())
  } catch (error) {
    ElMessage.error(error.message || '登录失败，请检查用户名和密码')
  } finally {
    loginLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 22%),
    radial-gradient(circle at bottom right, rgba(245, 158, 11, 0.12), transparent 22%),
    var(--app-login-bg);
}

.login-page__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: min(960px, 100%);
  margin: 0 auto 32px;
}

.login-page__brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.login-page__brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb 0%, #f59e0b 100%);
  box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.12);
}

.login-page__brand-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.login-page__brand-subtitle {
  color: var(--app-text-muted);
  font-size: 13px;
}

.login-page__theme-switch {
  box-shadow: var(--app-shadow-soft);
}

.login-page__theme-switch :deep(.el-switch__core) {
  --el-switch-on-color: var(--app-primary);
  --el-switch-off-color: var(--app-surface-elevated);
  border: 1px solid var(--app-border);
}

.login-page__main {
  display: flex;
  justify-content: center;
}

.login-page__panel {
  width: min(460px, 100%);
  padding: 32px;
  border: 1px solid color-mix(in srgb, var(--app-border) 88%, transparent);
  border-radius: 28px;
  background: color-mix(in srgb, var(--app-surface) 94%, transparent);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
}

.login-page__intro {
  margin-bottom: 24px;
}

.login-page__eyebrow {
  margin: 0 0 8px;
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.login-page__title {
  margin: 0;
  color: var(--app-text);
  font-size: 36px;
  line-height: 1.05;
}

.login-page__description {
  margin: 12px 0 0;
  color: var(--app-text-soft);
  line-height: 1.7;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-form :deep(.el-form-item__label) {
  color: var(--app-text);
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--app-surface-elevated) 88%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--app-border) 82%, transparent) inset;
}

.login-form__submit {
  width: 100%;
  height: 48px;
  margin-top: 6px;
  border-radius: 14px;
}

.login-page__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.login-page__hint {
  padding: 7px 12px;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  color: var(--app-text-muted);
  font-size: 12px;
  background: color-mix(in srgb, var(--app-surface-elevated) 78%, transparent);
}

@media (max-width: 640px) {
  .login-page {
    padding: 14px;
  }

  .login-page__topbar {
    margin-bottom: 18px;
  }

  .login-page__panel {
    padding: 22px;
    border-radius: 22px;
  }

  .login-page__title {
    font-size: 30px;
  }
}
</style>
