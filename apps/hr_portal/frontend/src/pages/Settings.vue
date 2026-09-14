<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="HR Settings"
        description="Organization, employee codes, and hire catalogs. One company only."
      />
    </template>

    <div class="max-w-3xl">
      <LoadingIndicator v-if="loading" />
      <form v-else class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <FormControl v-model="form.company_name" label="Company name" required class="sm:col-span-2" />
        <FormControl v-model="form.legal_name" label="Legal name" />
        <FormControl v-model="form.gstin" label="GSTIN" />
        <FormControl v-model="form.timezone" label="Timezone" required />
        <FormControl v-model="form.currency" label="Currency" required />
        <FormControl v-model="form.work_week" label="Work week" />
        <FormControl v-model.number="form.late_grace_minutes" label="Late grace (minutes)" type="number" min="0" />
        <FormControl v-model="form.employee_code_prefix" label="Employee code prefix" />
        <FormControl v-model.number="form.employee_code_padding" label="Padding" type="number" min="1" />
        <FormControl v-model.number="form.employee_code_next_sequence" label="Next sequence" type="number" min="1" />
        <FormControl
          v-model="autoGenerateChecked"
          label="Auto-generate employee codes"
          type="checkbox"
          class="sm:col-span-2"
        />
        <FormControl
          v-model="geofencingChecked"
          label="Geofencing enabled"
          type="checkbox"
          class="sm:col-span-2"
        />
        <FormControl v-model="form.departments" label="Departments (one per line)" type="textarea" rows="4" class="sm:col-span-2" />
        <FormControl v-model="form.designations" label="Designations (one per line)" type="textarea" rows="4" class="sm:col-span-2" />
        <FormControl v-model="form.primary_color" label="Primary color" />
        <FormControl v-model="form.email_sender_name" label="Email sender name" />
        <FormAlerts :error="error" :success="saved ? 'Saved.' : ''" class="sm:col-span-2" />
        <div class="sm:col-span-2">
          <Button type="submit" variant="solid" :loading="pending">Save settings</Button>
        </div>
      </form>

      <Card title="Audit log" subtitle="Recent payroll and domain events." class="mt-10">
        <DataList
          :items="auditLogs"
          :columns="auditColumns"
          :header-columns="auditHeaders"
          empty-text="No audit entries yet."
          row-class=""
        >
          <template #row="{ item }">
            <ListCell>
              <span class="whitespace-nowrap text-base text-ink-gray-7">{{ item.createdAt }}</span>
            </ListCell>
            <ListCell>
              <span class="text-base text-ink-gray-8">{{ item.action }}</span>
            </ListCell>
            <ListCell>
              <span class="truncate text-base text-ink-gray-7">
                {{ item.entityType }} · {{ item.entityId || '—' }}
              </span>
            </ListCell>
            <ListCell>
              <span class="truncate text-base text-ink-gray-7">{{ item.actorUserId }}</span>
            </ListCell>
          </template>
        </DataList>
      </Card>

      <Card title="3PL vendors" class="mt-10">
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="saveVendor">
          <FormControl v-model="vendor.vendor_name" label="Vendor name" required />
          <FormControl v-model="vendor.contact_name" label="Contact" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="subtle" :loading="vendorPending">Add vendor</Button>
          </div>
        </form>
        <DataList
          class="mt-4"
          :items="vendors"
          :columns="vendorColumns"
          :header-columns="vendorHeaders"
          empty-text="No vendors yet."
          row-class=""
        >
          <template #row="{ item }">
            <ListCell>
              <span class="truncate text-base text-ink-gray-8">{{ item.vendor_name }}</span>
            </ListCell>
            <ListCell>
              <Badge :label="item.status" :theme="item.status === 'Active' ? 'green' : 'gray'" />
            </ListCell>
          </template>
        </DataList>
      </Card>
    </div>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Badge, Button, call, createListResource, FormControl, LoadingIndicator } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError } from '@/lib/error'

const loading = ref(true)
const pending = ref(false)
const vendorPending = ref(false)
const error = ref('')
const saved = ref(false)
const form = reactive({
  company_name: '',
  legal_name: '',
  gstin: '',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  work_week: '',
  late_grace_minutes: 15,
  employee_code_prefix: 'EMP',
  employee_code_padding: 4,
  employee_code_next_sequence: 1,
  employee_code_auto_generate: 1,
  geofencing: 1,
  departments: '',
  designations: '',
  primary_color: '#1A3A6B',
  email_sender_name: '',
})
const vendor = reactive({ vendor_name: '', contact_name: '' })
const vendorList = createListResource({
  doctype: 'HR Vendor',
  fields: ['name', 'vendor_name', 'status'],
  auto: true,
  pageLength: 50,
})
const vendors = computed(() => vendorList.data || [])
const auditLogs = ref([])
const auditColumns = ['11rem', '10rem', 'minmax(0,1.2fr)', 'minmax(0,1fr)']
const auditHeaders = [
  { key: 'when', label: 'When' },
  { key: 'action', label: 'Action' },
  { key: 'entity', label: 'Entity' },
  { key: 'actor', label: 'Actor' },
]
const vendorColumns = ['minmax(0,1fr)', '8rem']
const vendorHeaders = [
  { key: 'name', label: 'Vendor' },
  { key: 'status', label: 'Status' },
]

const autoGenerateChecked = computed({
  get: () => Boolean(form.employee_code_auto_generate),
  set: (value) => {
    form.employee_code_auto_generate = value ? 1 : 0
  },
})

const geofencingChecked = computed({
  get: () => Boolean(form.geofencing),
  set: (value) => {
    form.geofencing = value ? 1 : 0
  },
})

onMounted(async () => {
  const [data, logs] = await Promise.all([
    call('hr_portal.api.settings.get_settings'),
    call('hr_portal.api.audit.list_audit_logs', { limit: 30 }).catch(() => []),
  ])
  Object.assign(form, data)
  auditLogs.value = logs || []
  loading.value = false
})

async function save() {
  error.value = ''
  saved.value = false
  pending.value = true
  try {
    const data = await call('hr_portal.api.settings.save_settings', { ...form })
    Object.assign(form, data)
    saved.value = true
  } catch (e) {
    error.value = apiError(e, 'Unable to save settings')
  } finally {
    pending.value = false
  }
}

async function saveVendor() {
  vendorPending.value = true
  try {
    await call('hr_portal.api.masters.save_vendor', { ...vendor })
    vendor.vendor_name = ''
    vendor.contact_name = ''
    vendorList.reload()
  } catch (e) {
    error.value = apiError(e, 'Unable to save vendor')
  } finally {
    vendorPending.value = false
  }
}
</script>
