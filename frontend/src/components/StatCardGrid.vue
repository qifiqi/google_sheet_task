<template>
  <el-row :gutter="16" class="stat-card-grid">
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
.stat-card-grid {
  margin-bottom: 20px;
}

.stat-card-grid__col {
  margin-bottom: 16px;
  display: flex;
}

.stat-card {
  width: 100%;
  padding: 18px 20px;
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  transition: box-shadow 0.2s, transform 0.2s;
  display: flex;
  flex-direction: column;
  justify-content: center;

  &:hover {
    box-shadow: var(--app-shadow-md);
    transform: translateY(-1px);
  }

  &__label {
    font-size: var(--app-font-xs);
    font-weight: 500;
    color: var(--app-text-muted);
    margin-bottom: 6px;
    line-height: 1.4;
  }

  &__value {
    font-size: 28px;
    font-weight: 700;
    color: var(--app-text);
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
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
      color: rgba(255, 255, 255, 0.85);
    }

    .stat-card__value {
      color: #fff;
    }

    &:hover {
      box-shadow: var(--app-shadow-lg);
    }
  }
}
</style>
