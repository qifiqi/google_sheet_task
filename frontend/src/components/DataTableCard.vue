<template>
  <el-card shadow="never" class="data-table-card">
    <div v-if="title || $slots['header-extra']" class="data-table-card__head">
      <div class="data-table-card__title">{{ title }}</div>
      <div class="data-table-card__extra">
        <slot name="header-extra" />
      </div>
    </div>

    <el-table
      :data="data"
      v-loading="loading"
      :stripe="stripe"
      class="data-table-card__table"
      v-bind="$attrs"
    >
      <slot />
      <template #empty>
        <slot name="empty">
          <el-empty description="暂无数据" :image-size="80" />
        </slot>
      </template>
    </el-table>

    <div v-if="showPagination && total > 0" class="data-table-card__pagination">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="pageSizes"
        :layout="paginationLayout"
        @update:current-page="handlePageChange"
        @update:page-size="handleSizeChange"
      />
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { useResponsive } from '@/composables/useResponsive'

const props = defineProps({
  title: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  data: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  pageSizes: { type: Array, default: () => [10, 20, 50] },
  stripe: { type: Boolean, default: true },
  showPagination: { type: Boolean, default: true },
})

const emit = defineEmits(['update:page', 'update:pageSize', 'page-change', 'refresh'])

const { isMobile } = useResponsive()

const paginationLayout = computed(() =>
  isMobile.value ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'
)

function handlePageChange(val) {
  emit('update:page', val)
  emit('page-change')
}

function handleSizeChange(val) {
  emit('update:pageSize', val)
  emit('update:page', 1)
  emit('page-change')
}
</script>

<style lang="scss" scoped>
@use '../styles/mixins' as *;

.data-table-card {
  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  &__title {
    font-size: var(--app-font-sm);
    font-weight: 600;
    color: var(--app-text);
  }

  &__extra {
    font-size: var(--app-font-xs);
    color: var(--app-text-muted);
  }

  &__pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;

    @include mobile {
      justify-content: center;
    }
  }
}
</style>
