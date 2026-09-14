<template>
  <div>
    <h1 class="text-xl font-semibold">{{ title }}</h1>
    <p class="mt-2 text-sm text-gray-600">
      This screen is a Phase {{ phase }} placeholder. The Frappe DocType and API are not wired yet.
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => route.meta.title || 'Coming soon')
const phase = computed(() => route.meta.phase || 'later')
</script>
