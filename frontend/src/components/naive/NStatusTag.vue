<template>
  <n-tag :type="tagType" :bordered="false" size="small" round>
    {{ label }}
  </n-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'pending' },
})

const statusMap = {
  pending: { type: 'default', label: '待执行' },
  running: { type: 'warning', label: '运行中' },
  completed: { type: 'success', label: '已完成' },
  cancelled: { type: 'default', label: '已取消' },
  error: { type: 'error', label: '错误' },
}

const tagType = computed(() => statusMap[props.status]?.type || 'default')
const label = computed(() => statusMap[props.status]?.label || props.status)
</script>
