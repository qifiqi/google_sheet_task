<template>
  <div style="padding: 40px; font-family: sans-serif;">
    <h1>任务执行平台</h1>
    <p>前后端分离版本 — Vue 3 + Vite</p>

    <div v-if="loading">加载中...</div>
    <div v-else>
      <h3>可用版本</h3>
      <ul>
        <li v-for="v in versions" :key="v.value">
          {{ v.label }} — <code>{{ v.create_url }}</code>
        </li>
      </ul>

      <h3>枚举值</h3>
      <pre>{{ JSON.stringify(enums, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getVersions, getEnums } from '../api/meta'

const loading = ref(true)
const versions = ref([])
const enums = ref({})

onMounted(async () => {
  try {
    const [vRes, eRes] = await Promise.all([getVersions(), getEnums()])
    versions.value = vRes.data
    enums.value = eRes.data
  } finally {
    loading.value = false
  }
})
</script>
