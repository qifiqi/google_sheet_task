<template>
  <div class="n-stat-grid">
    <div v-for="card in cards" :key="card.key" class="n-stat-grid__item">
      <div class="n-stat-card" :style="{ '--accent': card.color || '#6366f1' }">
        <div class="n-stat-card__label">{{ card.label }}</div>
        <div class="n-stat-card__value">{{ data[card.key] ?? '-' }}</div>
        <div v-if="card.hint" class="n-stat-card__hint">{{ card.hint }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  cards: { type: Array, required: true },
  data: { type: Object, default: () => ({}) },
})
</script>

<style scoped>
.n-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.n-stat-card {
  position: relative;
  padding: 16px 18px;
  border-radius: 14px;
  background: #111827;
  border: 1px solid rgba(148, 163, 184, 0.1);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.n-stat-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--accent);
  border-radius: 4px 0 0 4px;
}

.n-stat-card:hover {
  border-color: rgba(99, 102, 241, 0.25);
  box-shadow: 0 4px 24px rgba(99, 102, 241, 0.08);
}

.n-stat-card__label {
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  margin-bottom: 6px;
}

.n-stat-card__value {
  font-size: 26px;
  font-weight: 700;
  color: #f1f5f9;
  line-height: 1;
}

.n-stat-card__hint {
  margin-top: 6px;
  font-size: 11px;
  color: #64748b;
}

@media (max-width: 768px) {
  .n-stat-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .n-stat-card {
    padding: 12px 14px;
  }

  .n-stat-card__value {
    font-size: 20px;
  }
}
</style>
