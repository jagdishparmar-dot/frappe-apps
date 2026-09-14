<template>
  <div class="flex min-w-0 flex-col gap-0.5">
    <Breadcrumbs v-if="items?.length" :items="normalizedItems" />
    <h1 v-if="title" class="truncate text-lg font-medium text-ink-gray-9">
      {{ title }}
    </h1>
    <p v-if="description" class="truncate text-sm text-ink-gray-6">
      {{ description }}
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Breadcrumbs } from 'frappe-ui'

const props = defineProps({
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  items: { type: Array, default: () => [] },
})

const normalizedItems = computed(() =>
  (props.items || []).map((item) => ({
    label: item.label,
    route: item.route || item.to,
    href: item.href,
  })),
)
</script>
