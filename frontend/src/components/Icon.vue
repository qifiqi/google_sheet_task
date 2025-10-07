<template>
  <component :is="iconComponent" v-bind="$attrs" />
</template>

<script setup>
import { defineAsyncComponent, computed } from 'vue'

const props = defineProps({
  name: {
    type: String,
    required: true
  }
})

// 按需加载图标组件
const iconComponent = computed(() => {
  return defineAsyncComponent(() => 
    import(`@element-plus/icons-vue`).then(module => {
      const IconComponent = module[props.name]
      if (!IconComponent) {
        console.warn(`Icon "${props.name}" not found`)
        return { template: '<span></span>' }
      }
      return IconComponent
    }).catch(() => {
      console.warn(`Failed to load icon "${props.name}"`)
      return { template: '<span></span>' }
    })
  )
})
</script>
