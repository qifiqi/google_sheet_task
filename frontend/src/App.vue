<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>

<template>
  <el-config-provider namespace="el" :locale="zhCn" size="default" :z-index="3000">
    <router-view />
  </el-config-provider>
</template>
