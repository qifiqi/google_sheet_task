<template>
  <el-row :gutter="12" class="stat-card-grid">
    <el-col
      v-for="card in cards"
      :key="card.key"
      :xs="columns.xs"
      :sm="columns.sm"
      :md="columns.md"
      class="stat-card-grid__col"
    >
      <slot name="card" :card="card" :value="data[card.key]">
        <div class="stat-card" :style="{ '--accent': card.color || 'var(--app-primary)' }">
          <div class="stat-card__label">{{ card.label }}</div>
          <div class="stat-card__value">{{ data[card.key] ?? 0 }}</div>
          <div v-if="card.hint" class="stat-card__hint">{{ card.hint }}</div>
        </div>
      </slot>
    </el-col>
  </el-row>
</template>

<script setup>
defineProps({
  cards: { type: Array, required: true },
  data: { type: Object, default: () => ({}) },
  columns: { type: Object, default: () => ({ xs: 12, sm: 6, md: 6 }) },
})
</script>

<style lang="scss" scoped>
.stat-card-grid__col {
  margin-bottom: 12px;
}

// 全站统一的统计卡：surface 底 + 左侧彩色 accent 条，跨页风格一致
.stat-card {
  position: relative;
  padding: 14px 16px 14px 20px;
  border-radius: var(--el-border-radius-base);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  overflow: hidden;
  transition: box-shadow 0.2s;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: var(--accent);
  }

  &:hover {
    box-shadow: var(--app-shadow-soft);
  }

  &__label {
    font-size: var(--app-font-xs);
    color: var(--app-text-muted);
    margin-bottom: 4px;
  }

  &__value {
    font-size: 26px;
    font-weight: 700;
    color: var(--app-text);
    line-height: 1.2;
  }

  &__hint {
    font-size: 12px;
    color: var(--app-text-muted);
    margin-top: 4px;
  }
}
</style>
