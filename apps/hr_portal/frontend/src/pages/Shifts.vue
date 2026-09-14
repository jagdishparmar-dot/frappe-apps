<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Shifts"
        description="Shift catalog, roster assignments, and change requests."
      />
    </template>

    <TabButtons v-model="tab" :options="tabButtons" />

    <template v-if="tab === 'catalog'">
      <Card :title="form.name ? 'Edit shift' : 'New shift'" class="mt-6 max-w-3xl">
        <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
          <FormControl v-model="form.shift_name" label="Name" required />
          <FormControl v-model="form.code" label="Code" required />
          <FormControl v-model="form.start_time" label="Start" type="time" required />
          <FormControl v-model="form.end_time" label="End" type="time" required />
          <FormControl v-model="form.shift_type" label="Type" type="select" :options="shiftTypeOptions" />
          <FormControl v-model="form.status" label="Status" type="select" :options="statusOptions" />
          <FormAlerts :error="error" class="sm:col-span-2" />
          <div class="sm:col-span-2 flex gap-2">
            <Button type="submit" variant="solid" :loading="pending">Save shift</Button>
            <Button v-if="form.name" variant="subtle" type="button" @click="resetForm">Clear</Button>
          </div>
        </form>
      </Card>

      <DataList
        class="mt-6"
        :items="shifts.data || []"
        :columns="shiftColumns"
        :header-columns="shiftHeaders"
        @row-click="edit"
      >
        <template #row="{ item }">
          <ListCell>
            <span class="truncate text-base text-ink-gray-8">{{ item.shift_name }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.code }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.start_time }} – {{ item.end_time }}</span>
          </ListCell>
          <ListCell>
            <Badge :label="item.status" :theme="item.status === 'Active' ? 'green' : 'gray'" />
          </ListCell>
        </template>
      </DataList>
    </template>

    <template v-else>
      <Card title="Generate rotational roster" class="mt-6 max-w-3xl">
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="generate">
          <FormControl
            v-model="rosterForm.employee"
            label="Employee"
            type="select"
            :options="employeeOptions"
            required
            class="sm:col-span-2"
          />
          <DatePicker v-model="rosterForm.start_date" label="Start date" required />
          <FormControl v-model.number="rosterForm.days" label="Days" type="number" min="1" max="60" />
          <FormControl v-model="rosterForm.pattern" label="Pattern (e.g. GEN,B,OFF,GEN)" required class="sm:col-span-2" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="solid" :loading="rosterPending">Generate</Button>
          </div>
        </form>
      </Card>

      <Card title="Import CSV" class="mt-4 max-w-3xl">
        <form class="grid gap-3" @submit.prevent="importCsv">
          <input type="file" accept=".csv,text/csv" @change="onCsvFile" />
          <div>
            <Button type="submit" variant="outline" :loading="importPending" :disabled="!csvText">Import roster</Button>
          </div>
          <ErrorMessage :message="importErrors.join(' ')" />
        </form>
      </Card>

      <div class="mt-6 flex flex-wrap gap-2 items-end">
        <DatePicker v-model="range.from" label="From" />
        <DatePicker v-model="range.to" label="To" />
        <Button variant="outline" @click="loadRoster">Refresh</Button>
      </div>

      <DataList
        class="mt-4"
        :items="assignments"
        :columns="rosterColumns"
        :header-columns="rosterHeaders"
        empty-text="No roster assignments in this range."
        row-class=""
      >
        <template #row="{ item }">
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.dateIso }}</span>
          </ListCell>
          <ListCell>
            <span class="truncate text-base text-ink-gray-8">{{ item.employeeName }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.shiftCode || item.shiftName }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.sequence }}</span>
          </ListCell>
        </template>
      </DataList>

      <div v-if="changeRequests.length" class="mt-8">
        <h2 class="font-medium text-ink-gray-9">Pending shift change requests</h2>
        <div class="mt-3 space-y-2">
          <Card v-for="item in changeRequests.filter((r) => r.status === 'pending')" :key="item.id">
            <div class="flex justify-between gap-3">
              <div class="text-sm">
                <p class="font-medium">{{ item.employeeName }}</p>
                <p>{{ item.dateIso }} · {{ item.currentShiftCode || '—' }} → {{ item.requestedShiftCode }}</p>
              </div>
              <div class="flex gap-2">
                <Button size="sm" variant="solid" @click="reviewChange(item.id, 'approved')">Approve</Button>
                <Button size="sm" variant="outline" @click="reviewChange(item.id, 'rejected')">Reject</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </template>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Badge, Button, call, createListResource, DatePicker, ErrorMessage, FormControl, TabButtons } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError } from '@/lib/error'
import { selectOptions } from '@/lib/form'

const tab = ref('catalog')
const pending = ref(false)
const rosterPending = ref(false)
const importPending = ref(false)
const error = ref('')
const employees = ref([])
const assignments = ref([])
const changeRequests = ref([])
const csvText = ref('')
const importErrors = ref([])
const range = reactive({
  from: new Date().toISOString().slice(0, 10),
  to: new Date(Date.now() + 13 * 86400000).toISOString().slice(0, 10),
})
const rosterForm = reactive({
  employee: '',
  start_date: new Date().toISOString().slice(0, 10),
  days: 7,
  pattern: '',
})
const form = reactive({
  name: '',
  shift_name: '',
  code: '',
  start_time: '09:00',
  end_time: '18:00',
  shift_type: 'general',
  status: 'Active',
})

const tabButtons = [
  { label: 'Catalog', value: 'catalog' },
  { label: 'Roster', value: 'roster' },
]

const shiftTypeOptions = [
  { label: 'General', value: 'general' },
  { label: 'Evening', value: 'evening' },
  { label: 'Night', value: 'night' },
  { label: 'Rotational', value: 'rotational' },
  { label: 'Cross midnight', value: 'cross_midnight' },
]
const statusOptions = selectOptions(['Active', 'Inactive'])
const shiftColumns = ['minmax(0,1fr)', '7rem', '12rem', '7rem']
const shiftHeaders = [
  { key: 'name', label: 'Name' },
  { key: 'code', label: 'Code' },
  { key: 'hours', label: 'Hours' },
  { key: 'status', label: 'Status' },
]
const rosterColumns = ['9rem', 'minmax(0,1fr)', '9rem', '5rem']
const rosterHeaders = [
  { key: 'date', label: 'Date' },
  { key: 'employee', label: 'Employee' },
  { key: 'shift', label: 'Shift' },
  { key: 'seq', label: 'Seq' },
]

const employeeOptions = computed(() => {
  const rows = (employees.value || []).map((row) => ({
    label: `${row.employee_name} (${row.employee_code})`,
    value: row.name,
  }))
  return [{ label: 'Select employee', value: '' }, ...rows]
})

const shifts = createListResource({
  doctype: 'HR Shift',
  fields: ['name', 'shift_name', 'code', 'start_time', 'end_time', 'shift_type', 'status'],
  orderBy: 'shift_name',
  auto: true,
  pageLength: 100,
})

function timeValue(value) {
  const text = String(value || '')
  return text.length >= 5 ? text.slice(0, 5) : text
}

function edit(row) {
  Object.assign(form, row)
  form.start_time = timeValue(row.start_time)
  form.end_time = timeValue(row.end_time)
}

function resetForm() {
  form.name = ''
  form.shift_name = ''
  form.code = ''
  form.start_time = '09:00'
  form.end_time = '18:00'
  form.shift_type = 'general'
  form.status = 'Active'
}

async function save() {
  error.value = ''
  pending.value = true
  try {
    await call('hr_portal.api.masters.save_shift', { ...form })
    resetForm()
    shifts.reload()
  } catch (e) {
    error.value = apiError(e, 'Unable to save shift')
  } finally {
    pending.value = false
  }
}

async function loadEmployees() {
  employees.value = await call('frappe.client.get_list', {
    doctype: 'HR Employee',
    fields: ['name', 'employee_name', 'employee_code'],
    filters: { status: 'Active' },
    limit_page_length: 500,
  })
}

async function loadRoster() {
  const data = await call('hr_portal.api.shifts.list_assignments', { from_date: range.from, to_date: range.to })
  assignments.value = data.assignments || []
  const changes = await call('hr_portal.api.shifts.list_change_requests')
  changeRequests.value = changes.requests || []
}

async function generate() {
  rosterPending.value = true
  try {
    await call('hr_portal.api.shifts.generate_roster', { ...rosterForm })
    await loadRoster()
  } finally {
    rosterPending.value = false
  }
}

function onCsvFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    csvText.value = String(reader.result || '')
  }
  reader.readAsText(file)
}

async function importCsv() {
  importPending.value = true
  importErrors.value = []
  try {
    const data = await call('hr_portal.api.shifts.import_roster', { csv_text: csvText.value })
    importErrors.value = data.errors || []
    await loadRoster()
  } finally {
    importPending.value = false
  }
}

async function reviewChange(id, decision) {
  await call('hr_portal.api.shifts.review_change_request', { request_id: id, decision })
  await loadRoster()
}

watch(tab, (value) => {
  if (value === 'roster') loadRoster()
})

onMounted(loadEmployees)
</script>
