<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="access-denied-page">
    <el-result icon="warning" title="没有访问权限" sub-title="当前账户无权访问此页面。">
      <template #extra>
        <el-button type="primary" @click="router.push({ name: 'Dashboard' })">返回工作台</el-button>
      </template>
    </el-result>
  </section>
</template>

<style scoped>
.access-denied-page { min-height: 420px; display: grid; place-items: center; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
</style>
