<template>
  <nav class="sidebar-menu" :class="{ 'is-loading': isLoading }">
    <div v-if="isLoading" class="sidebar-menu__skeleton">
      <div v-for="i in 6" :key="i" class="skeleton" :style="{ height: i <= 2 ? '14px' : '36px', marginBottom: '8px', width: i <= 2 ? '60%' : '90%' }" />
    </div>

    <ul v-else class="sidebar-menu__list">
      <SidebarMenuItem
        v-for="item in navItems"
        :key="item.key"
        :item="item"
      />
    </ul>
  </nav>
</template>

<script setup>
import { onMounted, computed } from 'vue'
import { useNavigation } from '@/composables/useNavigation'
import SidebarMenuItem from './SidebarMenuItem.vue'

const { navItems, ensureNavLoaded } = useNavigation()

const isLoading = computed(() => navItems.value.length === 0)

onMounted(() => {
  ensureNavLoaded()
})
</script>

<style lang="scss" scoped>
.sidebar-menu {
  padding: 8px 10px;

  &__list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  &__skeleton {
    padding: 16px 14px;
  }

  &.is-loading {
    opacity: 0.6;
  }
}
</style>
