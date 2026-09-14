<template>
  <slot name="header" />
  <div :class="bodyClass">
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** `page` = default shell padding; `form` = centered form column; `full` = no padding */
  layout: {
    type: String,
    default: 'page',
  },
})

const bodyClass = computed(() => {
  if (props.layout === 'full') return ''
  if (props.layout === 'form') return 'p-4'
  return 'p-4'
})
</script>
