<template>
  <div v-if="error || success" class="space-y-2">
    <Alert v-if="error" theme="red" :title="error" />
    <Alert v-if="success" theme="green" :title="success" />
  </div>
</template>

<script setup>
import { Alert } from 'frappe-ui'

defineProps({
  error: { type: String, default: '' },
  success: { type: String, default: '' },
})
</script>
