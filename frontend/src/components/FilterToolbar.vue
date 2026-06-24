<template>
  <el-card shadow="never" class="filter-toolbar">
    <el-row :gutter="12" align="bottom">
      <el-col
        v-for="filter in filters"
        :key="filter.key"
        :xs="filter.span?.xs ?? 24"
        :sm="filter.span?.sm ?? 6"
        :md="filter.span?.md ?? 4"
      >
        <el-select
          v-if="filter.type === 'select'"
          :model-value="modelValue[filter.key]"
          :placeholder="filter.placeholder || filter.label || '请选择'"
          clearable
          class="full-width"
          @update:model-value="updateFilter(filter.key, $event)"
          @change="$emit('search')"
        >
          <el-option
            v-for="opt in filter.options"
            :key="opt.value"
            :value="opt.value"
            :label="opt.label"
          />
        </el-select>

        <el-input
          v-else-if="filter.type === 'input'"
          :model-value="modelValue[filter.key]"
          :placeholder="filter.placeholder || filter.label || '请输入'"
          clearable
          @update:model-value="updateFilterDebounced(filter.key, $event)"
          @keyup.enter="$emit('search')"
          @clear="$emit('search')"
        />

        <el-date-picker
          v-else-if="filter.type === 'date'"
          :model-value="modelValue[filter.key]"
          :placeholder="filter.placeholder || '选择日期'"
          type="date"
          value-format="YYYY-MM-DD"
          class="full-width"
          @update:model-value="updateFilter(filter.key, $event)"
          @change="$emit('search')"
        />
      </el-col>

      <el-col :xs="24" :sm="8" :md="4" class="filter-toolbar__btns">
        <el-button @click="$emit('clear')">清空</el-button>
        <el-button @click="$emit('search')">刷新</el-button>
        <slot name="extra" />
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { useDebounce } from '@/composables/useDebounce'

const props = defineProps({
  filters: { type: Array, required: true },
  modelValue: { type: Object, default: () => ({}) },
  debounceDelay: { type: Number, default: 300 },
})

const emit = defineEmits(['update:modelValue', 'search', 'clear'])
const { debounce } = useDebounce(props.debounceDelay)

function updateFilter(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function updateFilterDebounced(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
  debounce(() => emit('search'))
}
</script>

<style lang="scss" scoped>
.filter-toolbar {
  margin-bottom: 16px;
}

.filter-toolbar__btns {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.full-width {
  width: 100%;
}
</style>
