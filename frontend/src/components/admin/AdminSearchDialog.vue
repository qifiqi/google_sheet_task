<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import { Right, Search } from '@element-plus/icons-vue'
import type { NavItem } from '../../types/api'

const props = defineProps<{
  items: readonly NavItem[]
}>()

const emit = defineEmits<{
  select: [path: string]
}>()

const visible = defineModel<boolean>({ required: true })
const query = shallowRef('')

const results = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase('zh-CN')
  const matches = keyword
    ? props.items.filter((item) => `${item.label} ${item.path ?? ''}`.toLocaleLowerCase('zh-CN').includes(keyword))
    : props.items
  return matches.filter((item) => item.path).slice(0, 9)
})

watch(visible, (isVisible) => {
  if (!isVisible) query.value = ''
})

function choose(item: NavItem) {
  if (!item.path) return
  visible.value = false
  emit('select', item.path)
}

function chooseFirst() {
  const item = results.value[0]
  if (item) choose(item)
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="页面搜索"
    width="min(520px, calc(100vw - 28px))"
    top="12vh"
    append-to-body
    class="admin-search-dialog"
  >
    <el-input
      v-model="query"
      :prefix-icon="Search"
      placeholder="搜索页面"
      clearable
      autofocus
      @keyup.enter="chooseFirst"
    />
    <div class="admin-search-results">
      <button
        v-for="item in results"
        :key="item.key"
        type="button"
        class="admin-search-result"
        @click="choose(item)"
      >
        <span>
          <strong>{{ item.label }}</strong>
          <small>{{ item.path }}</small>
        </span>
        <el-icon><Right /></el-icon>
      </button>
      <el-empty v-if="!results.length" description="没有匹配页面" :image-size="62" />
    </div>
  </el-dialog>
</template>

<style scoped>
.admin-search-results {
  max-height: 360px;
  display: grid;
  gap: 4px;
  margin-top: 14px;
  overflow: auto;
}

.admin-search-result {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 8px 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--admin-text-regular);
  cursor: pointer;
  text-align: left;
}

.admin-search-result:hover,
.admin-search-result:focus-visible {
  outline: 0;
  background: var(--admin-primary-light);
  color: var(--admin-primary);
}

.admin-search-result > span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.admin-search-result strong {
  font-size: 13px;
}

.admin-search-result small {
  overflow: hidden;
  color: var(--admin-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
