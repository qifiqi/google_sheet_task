<template>
  <div class="login-container">
    <div class="login-grid">
      <section class="login-hero">
        <div class="login-hero__badge">Task Validation Platform</div>
        <h1 class="login-hero__title">让参数校验、任务编排和运行追踪集中在一个控制台里。</h1>
        <p class="login-hero__description">
          面向批量任务与 Google 参数校验场景设计的运营后台。统一查看版本任务、执行进度、异常状态和系统配置，不再在多个页面之间跳转。
        </p>

        <div class="login-hero__metrics">
          <div class="login-hero__metric">
            <span class="login-hero__metric-value">C3 / C4 / C5</span>
            <span class="login-hero__metric-label">多版本任务入口</span>
          </div>
          <div class="login-hero__metric">
            <span class="login-hero__metric-value">30s</span>
            <span class="login-hero__metric-label">实时刷新监控</span>
          </div>
          <div class="login-hero__metric">
            <span class="login-hero__metric-value">Sheets</span>
            <span class="login-hero__metric-label">数据通道联动</span>
          </div>
        </div>
      </section>

      <el-card class="login-card" shadow="never">
        <div class="login-card__eyebrow">欢迎回来</div>
        <h2 class="login-title">登录任务平台</h2>
        <p class="login-subtitle">使用你的账号进入任务列表、仪表盘和系统配置中心。</p>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
          <el-form-item prop="username" label="用户名">
            <el-input v-model.trim="form.username" placeholder="请输入用户名" size="large" />
          </el-form-item>
          <el-form-item prop="password" label="密码">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="handleLogin">
              进入控制台
            </el-button>
          </el-form-item>
        </el-form>

        <div class="login-footnote">
          建议使用桌面端获得完整的数据表格与批量操作体验。
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const { login } = useAuth()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value.validate()
  loading.value = true
  try {
    await login(form.username, form.password)
    router.push('/')
  } catch {
    ElMessage.error('登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 28px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.24), transparent 28%),
    radial-gradient(circle at bottom right, rgba(245, 158, 11, 0.16), transparent 24%),
    linear-gradient(180deg, #f7fafe 0%, #eef4fb 100%);
}

.login-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 420px);
  gap: 28px;
  width: min(1120px, 100%);
  align-items: stretch;
}

.login-hero {
  overflow: hidden;
  padding: 36px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.24), transparent 24%),
    linear-gradient(135deg, rgba(15, 29, 63, 0.98) 0%, rgba(22, 49, 95, 0.96) 45%, rgba(30, 64, 175, 0.92) 100%);
  color: #fff;
  box-shadow: 0 30px 60px rgba(15, 29, 63, 0.24);
}

.login-hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.84);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-hero__title {
  margin: 26px 0 14px;
  max-width: 580px;
  font-size: clamp(2rem, 1.45rem + 1.2vw, 3.4rem);
  line-height: 1.06;
  letter-spacing: -0.04em;
}

.login-hero__description {
  max-width: 560px;
  margin: 0;
  color: rgba(255, 255, 255, 0.8);
  font-size: 16px;
}

.login-hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 32px;
}

.login-hero__metric {
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
}

.login-hero__metric-value {
  display: block;
  font-family: 'Fira Code', monospace;
  font-size: 18px;
  font-weight: 600;
}

.login-hero__metric-label {
  display: block;
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.68);
  font-size: 12px;
}

.login-card {
  align-self: center;
  width: 100%;
}

.login-card__eyebrow {
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.login-title {
  margin: 10px 0 8px;
  color: var(--app-text);
  font-size: 30px;
  line-height: 1.1;
}

.login-subtitle {
  margin: 0 0 24px;
  color: var(--app-text-soft);
}

.login-submit {
  width: 100%;
  margin-top: 6px;
}

.login-footnote {
  padding-top: 6px;
  color: var(--app-text-muted);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 960px) {
  .login-container {
    padding: 18px;
  }

  .login-grid {
    grid-template-columns: 1fr;
  }

  .login-hero {
    padding: 24px;
    border-radius: 24px;
  }

  .login-hero__metrics {
    grid-template-columns: 1fr;
  }

  .login-title {
    font-size: 26px;
  }
}

@media (max-width: 640px) {
  .login-container {
    padding: 12px;
  }

  .login-hero {
    padding: 20px;
  }
}
</style>
