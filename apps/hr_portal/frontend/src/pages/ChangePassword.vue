<template>
  <div class="flex min-h-screen items-center justify-center bg-surface-gray-1 p-6">
    <Card title="Change password" subtitle="You must set a new password before using HR." class="w-full max-w-sm">
      <form class="space-y-4" @submit.prevent="submit">
        <FormControl
          v-model="currentPassword"
          label="Current password"
          type="password"
          required
        />
        <FormControl
          v-model="newPassword"
          label="New password"
          type="password"
          minlength="8"
          required
        />
        <ErrorMessage :message="error" />
        <Button type="submit" variant="solid" :loading="pending" class="w-full">Update password</Button>
      </form>
    </Card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, call, ErrorMessage, FormControl } from 'frappe-ui'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const session = useSessionStore()
const currentPassword = ref('')
const newPassword = ref('')
const error = ref('')
const pending = ref(false)

async function submit() {
  error.value = ''
  pending.value = true
  try {
    await call('hr_portal.api.auth.change_password', {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    session.session = null
    await session.load()
    router.replace({ name: session.isEmployeeOnly ? 'Me' : 'Home' })
  } catch (e) {
    error.value = e.messages?.[0] || e.message || 'Unable to change password'
  } finally {
    pending.value = false
  }
}
</script>
