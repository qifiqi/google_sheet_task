<template>
  <div class="mobile-card-list" v-loading="loading">
    <template v-if="data.length">
      <div
        v-for="(item, index) in data"
        :key="index"
        class="mobile-card-list__item"
        @click="$emit('item-click', item)"
      >
        <slot name="card" :item="item" :index="index" />
      </div>
    </template>
    <el-empty v-else-if="!loading" :description="emptyText" :image-size="80" />
  </div>
</template>

<script setup>
defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
})

defineEmits(['item-click'])
</script>

<style lang="scss" scoped>
.mobile-card-list {
  &__item {
    margin-bottom: 12px;
    cursor: pointer;
  }
}
</style>
