<template>
  <div class="flex min-h-screen items-center justify-center bg-surface-gray-1 p-6">
    <Alert
      theme="red"
      title="Not permitted"
      description="You do not have access to this HR portal area."
    />
  </div>
</template>

<script setup>
import { Alert } from 'frappe-ui'
</script>
