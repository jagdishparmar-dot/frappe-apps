<template>
  <Teleport v-if="showHeader" to="#app-header">
    <header class="flex h-10.5 items-center justify-between py-[7px] sm:pl-5 pl-2">
      <div class="flex min-w-0 items-center gap-2">
        <slot name="left-header" />
      </div>
      <div class="flex items-center gap-2">
        <slot name="right-header" />
      </div>
    </header>
  </Teleport>
</template>

<script setup>
import { nextTick, ref } from 'vue'

const showHeader = ref(false)

nextTick(() => {
  showHeader.value = true
})
</script>
