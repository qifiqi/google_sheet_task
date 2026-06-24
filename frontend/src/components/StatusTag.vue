<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ status: String })

const MAP = {
  pending:   { type: 'info',    label: '待执行' },
  running:   { type: 'warning', label: '运行中' },
  completed: { type: 'success', label: '已完成' },
  cancelled: { type: 'info',    label: '已取消' },
  error:     { type: 'danger',  label: '错误' },
}

const tagType = computed(() => MAP[props.status]?.type ?? '')
const label   = computed(() => MAP[props.status]?.label ?? props.status ?? '-')
</script>
