<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Dashboard"
        description="Today's attendance, workforce, and approval queues."
      />
    </template>

    <LoadingIndicator v-if="loading" class="mt-6" />
    <ErrorMessage v-else-if="error" class="mt-6">{{ error }}</ErrorMessage>
    <DashboardHome
      v-else-if="snapshot"
      :snapshot="snapshot"
      :company-name="session.companyName"
      :user-name="session.session?.full_name || ''"
      :roles="session.roles"
      :is-admin="isAdmin"
    />
  </PageContent>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { call, ErrorMessage, LoadingIndicator } from 'frappe-ui'
import DashboardHome from '@/components/DashboardHome.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const loading = ref(true)
const error = ref('')
const snapshot = ref(null)

const isAdmin = computed(() =>
  session.hasRole('HR Admin', 'HR Manager', 'System Manager'),
)

async function loadSnapshot() {
  loading.value = true
  error.value = ''
  try {
    snapshot.value = await call('hr_portal.api.dashboard.get_dashboard_snapshot')
  } catch (err) {
    error.value = err?.message || 'Could not load dashboard.'
  } finally {
    loading.value = false
  }
}

onMounted(loadSnapshot)
</script>
