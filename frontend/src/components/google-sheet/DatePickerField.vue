<script setup lang="ts">
defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ required: true })
</script>

<template>
  <el-date-picker v-model="model" v-bind="$attrs" />
</template>
