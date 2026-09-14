<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Attendance"
        description="Daily records, monthly export, and regularization queue."
      >
        <template #actions>
          <FormControl v-model="month" type="month" class="w-40" />
          <Button variant="outline" @click="exportCsv">Export CSV</Button>
        </template>
      </PageHeader>
    </template>

    <TabButtons v-model="tab" :options="tabButtons" />

    <LoadingIndicator v-if="loading" class="mt-6" />

    <DataList
      v-else-if="tab === 'records'"
      class="mt-6"
      :items="records"
      :columns="recordColumns"
      :header-columns="recordHeaders"
      empty-text="No attendance records yet."
      row-class=""
    >
      <template #row="{ item }">
        <ListCell>
          <span class="truncate text-base text-ink-gray-8">{{ item.employee_name || item.employee }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.date_iso }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.clock_in_time || '—' }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.clock_out_time || '—' }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.total_minutes ?? 0 }}</span>
        </ListCell>
        <ListCell>
          <Badge :label="item.status" :theme="statusTheme(item.status)" />
        </ListCell>
        <ListCell>
          <span class="truncate text-base text-ink-gray-7">{{ item.location_name || '—' }}</span>
        </ListCell>
      </template>
    </DataList>

    <div v-else class="mt-6 space-y-3">
      <Card v-for="item in regularizations" :key="item.id">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="font-medium">{{ item.employeeName }}</p>
            <p class="text-sm text-ink-gray-6">{{ item.dateIso }} · {{ item.reason }}</p>
            <p v-if="item.requestedClockIn || item.requestedClockOut" class="mt-1 text-sm">
              Requested: {{ item.requestedClockIn || '—' }} → {{ item.requestedClockOut || '—' }}
            </p>
            <Badge :label="item.status" :theme="statusTheme(item.status)" class="mt-2" />
          </div>
          <div v-if="item.status === 'pending'" class="flex gap-2">
            <Button size="sm" variant="solid" @click="review(item.id, 'approved')">Approve</Button>
            <Button size="sm" variant="outline" @click="review(item.id, 'rejected')">Reject</Button>
          </div>
        </div>
      </Card>
      <p v-if="!regularizations.length" class="text-sm text-ink-gray-6">No regularization requests.</p>
    </div>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Badge, Button, call, createListResource, FormControl, LoadingIndicator, TabButtons } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const canReview = computed(() => session.hasRole('HR Admin', 'HR Manager', 'System Manager'))
const tab = ref('records')
const loading = ref(true)
const month = ref(new Date().toISOString().slice(0, 7))
const regularizations = ref([])
const pendingCount = computed(() => regularizations.value.filter((r) => r.status === 'pending').length)

const tabButtons = computed(() => {
  const buttons = [{ label: 'Records', value: 'records' }]
  if (canReview.value) {
    buttons.push({
      label: pendingCount.value ? `Regularizations (${pendingCount.value})` : 'Regularizations',
      value: 'regularizations',
    })
  }
  return buttons
})

const recordColumns = [
  'minmax(0,1fr)',
  '8rem',
  '7rem',
  '7rem',
  '6rem',
  '8rem',
  'minmax(0,1fr)',
]
const recordHeaders = [
  { key: 'employee', label: 'Employee' },
  { key: 'date', label: 'Date' },
  { key: 'in', label: 'In' },
  { key: 'out', label: 'Out' },
  { key: 'minutes', label: 'Minutes' },
  { key: 'status', label: 'Status' },
  { key: 'location', label: 'Location' },
]

const attendance = createListResource({
  doctype: 'HR Attendance',
  fields: [
    'name',
    'employee',
    'date_iso',
    'clock_in_time',
    'clock_out_time',
    'total_minutes',
    'status',
    'location_name',
  ],
  orderBy: 'date_iso desc',
  auto: false,
  pageLength: 200,
})

const records = computed(() => {
  const rows = attendance.data || []
  return rows.map((row) => ({
    ...row,
    employee_name: row.employee_name || employeeNames.value[row.employee] || row.employee,
  }))
})

const employeeNames = ref({})

function statusTheme(status) {
  const value = String(status || '').toLowerCase()
  if (['present', 'approved'].includes(value)) return 'green'
  if (['pending', 'late', 'half-day'].includes(value)) return 'orange'
  if (['absent', 'rejected'].includes(value)) return 'red'
  return 'gray'
}

async function loadEmployees() {
  const emps = await call('frappe.client.get_list', {
    doctype: 'HR Employee',
    fields: ['name', 'employee_name'],
    limit_page_length: 500,
  })
  employeeNames.value = Object.fromEntries((emps || []).map((e) => [e.name, e.employee_name]))
}

async function loadRegularizations() {
  if (!canReview.value) return
  const data = await call('hr_portal.api.attendance.list_regularizations')
  regularizations.value = data.requests || []
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([attendance.reload(), loadEmployees(), loadRegularizations()])
  } finally {
    loading.value = false
  }
}

async function exportCsv() {
  const data = await call('hr_portal.api.attendance.export_register', { month: month.value })
  const blob = new Blob([data.csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = data.filename || `attendance-${month.value}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

async function review(id, decision) {
  await call('hr_portal.api.attendance.review_regularization', {
    regularization_id: id,
    decision,
    review_note: '',
  })
  await loadRegularizations()
  await attendance.reload()
}

onMounted(loadAll)
watch(tab, () => {
  if (tab.value === 'regularizations') loadRegularizations()
})
</script>
