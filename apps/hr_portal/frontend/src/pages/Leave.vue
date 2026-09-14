<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Leave"
        description="Types, holidays, balances, and approval queue."
      />
    </template>

    <TabButtons v-model="tab" :options="tabs" />

    <LoadingIndicator v-if="loading" class="mt-6" />

    <div v-else-if="tab === 'requests'" class="mt-6 space-y-3">
      <Card v-for="item in requests" :key="item.id">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="font-medium">{{ item.employeeName || item.employeeId }}</p>
            <p class="text-sm text-ink-gray-6">
              {{ item.leaveTypeName }} · {{ item.fromDate }} → {{ item.toDate }} ({{ item.days }}d)
            </p>
            <p v-if="item.note" class="mt-1 text-sm">{{ item.note }}</p>
            <Badge :label="item.status" :theme="statusTheme(item.status)" class="mt-2" />
          </div>
          <div v-if="canReview && item.status === 'pending'" class="flex gap-2">
            <Button size="sm" variant="solid" @click="review(item.id, 'approved')">Approve</Button>
            <Button size="sm" variant="outline" @click="review(item.id, 'rejected')">Reject</Button>
          </div>
        </div>
      </Card>
      <p v-if="!requests.length" class="text-sm text-ink-gray-6">No leave requests.</p>
    </div>

    <DataList
      v-else-if="tab === 'balances'"
      class="mt-6"
      :items="balances"
      :columns="balanceColumns"
      :header-columns="balanceHeaders"
      empty-text="No leave balances yet."
      row-class=""
    >
      <template #row="{ item }">
        <ListCell>
          <span class="truncate text-base text-ink-gray-8">
            {{ employeeNames[item.employeeId] || item.employeeId }}
          </span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.leaveTypeName }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.year }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-8">{{ item.balance }}</span>
        </ListCell>
      </template>
    </DataList>

    <div v-else-if="tab === 'types'" class="mt-6 grid max-w-3xl gap-4">
      <Card title="Leave type">
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="saveLeaveType">
          <FormControl v-model="typeForm.leave_type_name" label="Name" required />
          <FormControl v-model="typeForm.code" label="Code" required />
          <FormControl v-model.number="typeForm.accrual_per_month" label="Accrual / month" type="number" min="0" step="0.5" />
          <FormControl v-model.number="typeForm.max_balance" label="Max balance" type="number" min="0" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="solid" :loading="savingType">Save type</Button>
          </div>
        </form>
      </Card>

      <Card title="Holiday">
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="saveHoliday">
          <DatePicker v-model="holidayForm.holiday_date" label="Date" required />
          <FormControl v-model="holidayForm.holiday_name" label="Holiday name" required />
          <FormControl v-model="holidayForm.region" label="Region (optional)" class="sm:col-span-2" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="solid" :loading="savingHoliday">Save holiday</Button>
          </div>
        </form>
      </Card>

      <DataList
        class="mt-2"
        :items="holidays"
        :columns="holidayColumns"
        :header-columns="holidayHeaders"
        empty-text="No holidays configured yet."
        row-class=""
      >
        <template #row="{ item }">
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.date }}</span>
          </ListCell>
          <ListCell>
            <span class="truncate text-base text-ink-gray-8">{{ item.name }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-6">{{ item.region || '—' }}</span>
          </ListCell>
        </template>
      </DataList>
    </div>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Badge, Button, call, DatePicker, FormControl, LoadingIndicator, TabButtons } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const canReview = computed(() => session.hasRole('HR Admin', 'HR Manager', 'System Manager'))
const tab = ref('requests')
const loading = ref(true)
const requests = ref([])
const balances = ref([])
const holidays = ref([])
const employeeNames = ref({})
const savingType = ref(false)
const savingHoliday = ref(false)

const typeForm = reactive({
  leave_type_name: '',
  code: '',
  accrual_per_month: 1,
  max_balance: 24,
})
const holidayForm = reactive({
  holiday_date: '',
  holiday_name: '',
  region: '',
})

const pendingCount = computed(() => requests.value.filter((r) => r.status === 'pending').length)

const balanceColumns = ['minmax(0,1fr)', '10rem', '6rem', '7rem']
const balanceHeaders = [
  { key: 'employee', label: 'Employee' },
  { key: 'type', label: 'Type' },
  { key: 'year', label: 'Year' },
  { key: 'balance', label: 'Balance' },
]
const holidayColumns = ['9rem', 'minmax(0,1fr)', '10rem']
const holidayHeaders = [
  { key: 'date', label: 'Date' },
  { key: 'name', label: 'Holiday' },
  { key: 'region', label: 'Region' },
]

const tabs = computed(() => {
  const items = [
    {
      label: pendingCount.value ? `Requests (${pendingCount.value})` : 'Requests',
      value: 'requests',
    },
  ]
  if (canReview.value) {
    items.push({ label: 'Balances', value: 'balances' }, { label: 'Types & holidays', value: 'types' })
  }
  return items
})

function statusTheme(status) {
  const value = String(status || '').toLowerCase()
  if (value === 'approved') return 'green'
  if (value === 'pending') return 'orange'
  if (value === 'rejected') return 'red'
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

async function loadSnapshot() {
  loading.value = true
  try {
    const data = await call('hr_portal.api.leave.get_snapshot')
    requests.value = data.requests || []
    balances.value = data.balances || []
    holidays.value = data.holidays || []
    await loadEmployees()
  } finally {
    loading.value = false
  }
}

async function review(id, decision) {
  await call('hr_portal.api.leave.review_leave', { leave_request_id: id, decision })
  await loadSnapshot()
}

async function saveLeaveType() {
  savingType.value = true
  try {
    await call('hr_portal.api.masters.save_leave_type', { ...typeForm })
    typeForm.leave_type_name = ''
    typeForm.code = ''
    await loadSnapshot()
  } finally {
    savingType.value = false
  }
}

async function saveHoliday() {
  savingHoliday.value = true
  try {
    await call('hr_portal.api.masters.save_holiday', { ...holidayForm })
    holidayForm.holiday_name = ''
    holidayForm.region = ''
    await loadSnapshot()
  } finally {
    savingHoliday.value = false
  }
}

onMounted(loadSnapshot)
</script>
