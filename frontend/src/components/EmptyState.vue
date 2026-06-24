<template>
  <div class="empty-state">
    <el-empty :description="description">
      <template v-if="$slots.default" #description>
        <slot />
      </template>
      <template v-if="$slots.actions" #default>
        <slot name="actions" />
      </template>
    </el-empty>
  </div>
</template>

<script setup>
defineProps({
  description: { type: String, default: '暂无数据' },
})
</script>

<style lang="scss" scoped>
.empty-state {
  padding: 32px 16px;
}
</style>
