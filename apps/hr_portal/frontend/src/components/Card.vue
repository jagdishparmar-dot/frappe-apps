<template>
  <section class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
    <header v-if="title || subtitle || $slots.actions" class="mb-4 flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 v-if="title" class="text-base font-semibold text-ink-gray-9">{{ title }}</h3>
        <p v-if="subtitle" class="mt-0.5 text-sm text-ink-gray-6">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="shrink-0">
        <slot name="actions" />
      </div>
    </header>
    <LoadingIndicator v-if="loading" />
    <slot v-else />
  </section>
</template>

<script setup>
import { LoadingIndicator } from 'frappe-ui'

defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})
</script>
