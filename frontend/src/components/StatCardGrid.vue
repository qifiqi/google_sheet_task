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
        <div
          class="stat-card"
          :class="[variant ? `stat-card--${variant}` : '']"
          :style="cardStyle(card)"
        >
          <div class="stat-card__label">{{ card.label }}</div>
          <div class="stat-card__value">{{ data[card.key] ?? 0 }}</div>
          <div v-if="card.hint" class="stat-card__hint">{{ card.hint }}</div>
        </div>
      </slot>
    </el-col>
  </el-row>
</template>

<script setup>
const props = defineProps({
  cards: { type: Array, required: true },
  data: { type: Object, default: () => ({}) },
  columns: { type: Object, default: () => ({ xs: 12, sm: 6, md: 6 }) },
  variant: { type: String, default: '' },
})

function cardStyle(card) {
  const style = {}
  if (card.background) style.background = card.background
  if (card.color) style.color = card.color
  return style
}
</script>

<style lang="scss" scoped>
.stat-card-grid__col {
  margin-bottom: 12px;
}

.stat-card {
  padding: 16px 20px;
  border-radius: var(--el-border-radius-base);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: var(--app-shadow-soft);
  }

  &__label {
    font-size: var(--app-font-xs);
    color: var(--app-text-muted);
    margin-bottom: 4px;
  }

  &__value {
    font-size: 28px;
    font-weight: 700;
    color: var(--app-text);
    line-height: 1.2;
  }

  &__hint {
    font-size: 12px;
    color: var(--app-text-muted);
    margin-top: 4px;
  }

  &--gradient {
    border: none;
    color: #fff;

    .stat-card__label,
    .stat-card__hint {
      color: rgba(255, 255, 255, 0.8);
    }

    .stat-card__value {
      color: #fff;
    }
  }
}
</style>
