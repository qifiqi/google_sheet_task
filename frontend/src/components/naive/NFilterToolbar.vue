<template>
  <div class="n-filter-toolbar">
    <div class="n-filter-toolbar__fields">
      <template v-for="f in filters" :key="f.key">
        <n-select
          v-if="f.type === 'select'"
          :value="modelValue[f.key]"
          :options="f.options"
          :placeholder="f.placeholder || '全部'"
          clearable
          size="small"
          class="n-filter-toolbar__select"
          @update:value="(val) => updateField(f.key, val)"
        />
        <n-input
          v-else-if="f.type === 'input'"
          :value="modelValue[f.key]"
          :placeholder="f.placeholder || '搜索...'"
          clearable
          size="small"
          class="n-filter-toolbar__input"
          @update:value="(val) => updateField(f.key, val)"
          @keyup.enter="$emit('search')"
        />
      </template>
    </div>
    <div class="n-filter-toolbar__actions">
      <n-button size="small" @click="$emit('search')">搜索</n-button>
      <n-button size="small" quaternary @click="$emit('clear')">重置</n-button>
      <slot name="extra" />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  filters: { type: Array, required: true },
  modelValue: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue', 'search', 'clear'])

function updateField(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped>
.n-filter-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: #111827;
  border: 1px solid rgba(148, 163, 184, 0.1);
  flex-wrap: wrap;
}

.n-filter-toolbar__fields {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex: 1;
}

.n-filter-toolbar__select {
  width: 150px;
}

.n-filter-toolbar__input {
  width: 200px;
}

.n-filter-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 768px) {
  .n-filter-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .n-filter-toolbar__fields {
    flex-direction: column;
  }

  .n-filter-toolbar__select,
  .n-filter-toolbar__input {
    width: 100%;
  }

  .n-filter-toolbar__actions {
    justify-content: flex-end;
  }
}
</style>
