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
          <h1 class="login-page__title">{{ isSignupMode ? '注册申请' : '登录系统' }}</h1>
          <p class="login-page__description">
            {{ isSignupMode
              ? '当前项目未开放公开注册，保留申请入口与表单校验。'
              : '使用现有账号进入任务列表、回测结果和系统配置。' }}
          </p>
        </div>

        <div class="login-page__tabs">
          <button
            type="button"
            :class="['login-page__tab', { 'login-page__tab--active': !isSignupMode }]"
            @click="setMode(false)"
          >
            登录
          </button>
          <button
            type="button"
            :class="['login-page__tab', { 'login-page__tab--active': isSignupMode }]"
            @click="setMode(true)"
          >
            注册
          </button>
        </div>

        <transition name="login-fade" mode="out-in">
          <el-form
            v-if="!isSignupMode"
            key="login"
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
              :loading="loginLoading"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form>

          <el-form
            v-else
            key="signup"
            ref="signupFormRef"
            :model="signupForm"
            :rules="signupRules"
            label-position="top"
            class="login-form"
          >
            <el-form-item label="用户名" prop="username">
              <el-input v-model.trim="signupForm.username" size="large" placeholder="请输入用户名" />
            </el-form-item>

            <el-form-item label="邮箱" prop="email">
              <el-input v-model.trim="signupForm.email" size="large" placeholder="请输入邮箱" />
            </el-form-item>

            <el-form-item label="密码" prop="password">
              <el-input
                v-model="signupForm.password"
                size="large"
                type="password"
                placeholder="请输入密码"
                show-password
              />
            </el-form-item>

            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="signupForm.confirmPassword"
                size="large"
                type="password"
                placeholder="请再次输入密码"
                show-password
                @keyup.enter="handleSignup"
              />
            </el-form-item>

            <el-button
              size="large"
              class="login-form__submit login-form__submit--secondary"
              :loading="signupLoading"
              @click="handleSignup"
            >
              提交申请
            </el-button>
          </el-form>
        </transition>

        <footer class="login-page__footer">
          <span class="login-page__hint">Element Plus 官方组件</span>
          <span class="login-page__hint">明暗主题同步</span>
          <span class="login-page__hint">简洁后台风格</span>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAuth } from '@/composables/useAuth'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const { login } = useAuth()
const { switchValue } = useTheme()

const isSignupMode = ref(false)
const loginLoading = ref(false)
const signupLoading = ref(false)
const loginFormRef = ref()
const signupFormRef = ref()

const loginForm = reactive({
  username: '',
  password: '',
})

const signupForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const signupRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: ['blur', 'change'] },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_, value, callback) => {
        if (!value) callback(new Error('请再次输入密码'))
        else if (value !== signupForm.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: ['blur', 'change'],
    },
  ],
}

function setMode(value) {
  isSignupMode.value = value
}

async function handleLogin() {
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loginLoading.value = true
  try {
    await login(loginForm.username, loginForm.password)
    router.push('/')
  } catch {
    ElMessage.error('登录失败，请检查用户名和密码')
  } finally {
    loginLoading.value = false
  }
}

async function handleSignup() {
  const valid = await signupFormRef.value?.validate().catch(() => false)
  if (!valid) return

  signupLoading.value = true
  try {
    await new Promise((resolve) => setTimeout(resolve, 400))
    ElMessage.info('当前项目未开放公开注册，请联系管理员创建账号')
  } finally {
    signupLoading.value = false
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

.login-page__tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 6px;
  margin-bottom: 24px;
  border-radius: 16px;
  background: color-mix(in srgb, var(--app-surface-elevated) 86%, transparent);
}

.login-page__tab {
  height: 42px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--app-text-muted);
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.login-page__tab--active {
  background: var(--app-surface);
  color: var(--app-text);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
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

.login-form__submit--secondary {
  color: #fff;
  border: none;
  background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
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

.login-fade-enter-active,
.login-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.login-fade-enter-from,
.login-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
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
