<template>
  <div class="h-screen w-full bg-surface-base text-ink-gray-9">
    <DesktopShell>
      <template #sidebar>
        <AppSidebar />
      </template>
      <router-view />
    </DesktopShell>
  </div>
</template>

<script setup>
import { DesktopShell } from 'frappe-ui'
import AppSidebar from '@/components/Layouts/AppSidebar.vue'
</script>
