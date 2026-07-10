<script setup lang="ts">
import { computed, reactive, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const submitting = shallowRef(false)
const form = reactive({
  username: '',
  password: '',
})

const redirectTarget = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
})

async function submitLogin() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }

  submitting.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    ElMessage.success('登录成功')
    router.replace(redirectTarget.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-card__brand">
        <span>J</span>
        <div>
          <strong>JaspilAdmin</strong>
          <small>Task Operations Platform</small>
        </div>
      </div>
      <div class="login-card__copy">
        <h1>登录后台</h1>
        <p>使用现有 Flask 鉴权账户进入新工作台。</p>
      </div>
      <el-form class="login-card__form" @submit.prevent="submitLogin">
        <el-form-item>
          <el-input v-model="form.username" :prefix-icon="User" placeholder="用户名" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            placeholder="密码"
            show-password
            size="large"
            type="password"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <el-button class="login-card__submit" :loading="submitting" native-type="submit" size="large" type="primary">
          登录
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.1), rgba(16, 185, 129, 0.12)),
    var(--admin-bg);
}

.login-card {
  width: min(420px, 100%);
  padding: 32px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
  box-shadow: 0 24px 70px rgba(31, 42, 68, 0.12);
}

.login-card__brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.login-card__brand > span {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--admin-primary), #10b981);
  color: #fff;
  font-size: 22px;
  font-weight: 900;
}

.login-card__brand div,
.login-card__copy {
  display: grid;
  gap: 4px;
}

.login-card__brand strong {
  color: var(--admin-text);
  font-size: 18px;
}

.login-card__brand small,
.login-card__copy p {
  color: var(--admin-text-muted);
}

.login-card__copy {
  margin: 34px 0 24px;
}

.login-card__copy h1 {
  margin: 0;
  color: var(--admin-text);
  font-size: 28px;
  letter-spacing: 0;
}

.login-card__copy p {
  margin: 0;
  font-size: 14px;
}

.login-card__form {
  display: grid;
  gap: 4px;
}

.login-card__submit {
  width: 100%;
  margin-top: 8px;
}
</style>
