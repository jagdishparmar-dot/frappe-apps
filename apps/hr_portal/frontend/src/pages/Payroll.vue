<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Payroll"
        description="Run monthly payroll, review totals, and export bank CSV."
      />
    </template>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card title="Run payroll" subtitle="Payable days = min(22, present/late/half-day + approved leave). Pro-rates salary structure components.">
        <form class="space-y-3" @submit.prevent="run">
          <FormControl v-model="month" label="Payroll month" type="month" required />
          <Button type="submit" variant="solid" :loading="running">Run &amp; finalize payroll</Button>
          <FormAlerts :error="error" :success="ok" />
        </form>
      </Card>

      <Card title="Past runs" subtitle="Open a run to view printable payslips." :loading="loading">
        <DataList
          :items="runs"
          :columns="runColumns"
          :header-columns="runHeaders"
          empty-text="No payroll runs yet."
          row-class="cursor-pointer"
          @row-click="openRun"
        >
          <template #row="{ item }">
            <ListCell>
              <span class="text-base font-medium text-ink-blue-2">{{ item.month }}</span>
            </ListCell>
            <ListCell>
              <Badge :label="item.status" :theme="item.status === 'finalized' ? 'green' : 'gray'" />
            </ListCell>
            <ListCell>
              <span class="text-base text-ink-gray-7">{{ item.totals?.employees ?? 0 }}</span>
            </ListCell>
            <ListCell class="justify-end">
              <span class="text-base tabular-nums text-ink-gray-8">₹{{ formatMoney(item.totals?.totalNet) }}</span>
            </ListCell>
            <ListCell>
              <Button
                size="sm"
                variant="outline"
                :loading="exporting === item.id"
                @click.stop="downloadCsv(item)"
              >
                Bank CSV
              </Button>
            </ListCell>
          </template>
        </DataList>
      </Card>
    </div>
  </PageContent>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, call, FormControl } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError } from '@/lib/error'

const router = useRouter()
const loading = ref(true)
const runColumns = ['8rem', '8rem', '7rem', '9rem', '8rem']
const runHeaders = [
  { key: 'month', label: 'Month' },
  { key: 'status', label: 'Status' },
  { key: 'employees', label: 'Employees' },
  { key: 'net', label: 'Net total', align: 'end' },
  { key: 'actions', label: '' },
]
const running = ref(false)
const exporting = ref('')
const runs = ref([])
const error = ref('')
const ok = ref('')
const month = ref(new Date().toISOString().slice(0, 7))

onMounted(load)

async function load() {
  loading.value = true
  try {
    runs.value = await call('hr_portal.api.payroll.list_payroll_runs')
  } finally {
    loading.value = false
  }
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString('en-IN')
}

function openRun(run) {
  router.push({ name: 'PayrollRun', params: { runId: run.id } })
}

async function run() {
  error.value = ''
  ok.value = ''
  running.value = true
  try {
    const result = await call('hr_portal.api.payroll.run_payroll_action', { month: month.value })
    ok.value = `Payroll finalized (${result.payrollRunId}).`
    await load()
  } catch (e) {
    error.value = apiError(e, 'Payroll run failed')
  } finally {
    running.value = false
  }
}

async function downloadCsv(run) {
  exporting.value = run.id
  try {
    const result = await call('hr_portal.api.payroll.export_bank_csv_action', { payroll_run_id: run.id })
    const blob = new Blob([result.csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bank-export-${run.month}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = apiError(e, 'Export failed')
  } finally {
    exporting.value = ''
  }
}
</script>
