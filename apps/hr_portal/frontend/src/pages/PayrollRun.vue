<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Payslips"
        :description="`Run ${runId} — use browser print to save as PDF.`"
        class="print:hidden"
      >
        <template #actions>
          <Button variant="outline" @click="router.push({ name: 'Payroll' })">Back to payroll</Button>
        </template>
      </PageHeader>
    </template>

    <LoadingIndicator v-if="loading" class="print:hidden" />

    <div v-else class="space-y-4">
      <Card
        v-for="slip in slips"
        :key="slip.id"
        class="print:border-0 print:shadow-none"
      >
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-outline-gray-2 pb-3">
          <div>
            <h2 class="text-lg font-semibold text-ink-gray-9">{{ slip.employeeName || slip.employeeId }}</h2>
            <p class="text-sm text-ink-gray-6">{{ slip.employeeCode || '—' }} · {{ slip.month }}</p>
          </div>
          <div class="text-right">
            <p class="text-xl font-semibold tabular-nums text-ink-gray-9">₹{{ formatMoney(slip.netPay) }}</p>
            <Badge v-if="slip.status" :label="slip.status" :theme="slip.status === 'finalized' ? 'green' : 'gray'" class="mt-1" />
          </div>
        </div>
        <dl class="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt class="text-ink-gray-5">Payable days</dt>
            <dd class="font-medium">{{ slip.breakdown?.payableDays ?? '—' }} / {{ slip.breakdown?.workingDays ?? '—' }}</dd>
          </div>
          <div>
            <dt class="text-ink-gray-5">Present</dt>
            <dd class="font-medium">{{ slip.breakdown?.presentDays ?? '—' }}</dd>
          </div>
          <div>
            <dt class="text-ink-gray-5">Leave</dt>
            <dd class="font-medium">{{ slip.breakdown?.leaveDays ?? '—' }}</dd>
          </div>
          <div>
            <dt class="text-ink-gray-5">Gross</dt>
            <dd class="font-medium">₹{{ formatMoney(slip.breakdown?.gross) }}</dd>
          </div>
          <div>
            <dt class="text-ink-gray-5">Deductions</dt>
            <dd class="font-medium">₹{{ formatMoney(slip.breakdown?.deductions) }}</dd>
          </div>
        </dl>
        <div class="mt-4 print:hidden">
          <Button size="sm" variant="outline" @click="printSlip(slip.id)">Print payslip</Button>
        </div>
      </Card>
      <p v-if="!slips.length" class="text-sm text-ink-gray-6">No payslips for this run.</p>
    </div>
  </PageContent>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, call, LoadingIndicator } from 'frappe-ui'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'

const route = useRoute()
const router = useRouter()
const runId = route.params.runId
const loading = ref(true)
const slips = ref([])

onMounted(load)

async function load() {
  loading.value = true
  try {
    slips.value = await call('hr_portal.api.payroll.list_payslips', { payroll_run_id: runId })
  } finally {
    loading.value = false
  }
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString('en-IN')
}

async function printSlip(payslipId) {
  const detail = await call('hr_portal.api.payroll.get_payslip', { payslip_id: payslipId })
  const w = window.open('', '_blank', 'noopener,noreferrer')
  if (!w) return
  const components = (detail.breakdown?.components || [])
    .map((c) => `<tr><td>${c.label}</td><td style="text-align:right">${Number(c.amount).toFixed(2)}</td></tr>`)
    .join('')
  w.document.write(`
    <!doctype html><html><head><title>Payslip ${detail.month}</title>
    <style>body{font-family:system-ui,sans-serif;padding:24px}table{width:100%;border-collapse:collapse;margin-top:16px}td,th{padding:8px;border-bottom:1px solid #ddd}</style>
    </head><body>
    <h1>Payslip — ${detail.month}</h1>
    <p><strong>${detail.employee?.name || ''}</strong> (${detail.employee?.code || ''})</p>
    <p>${detail.employee?.department || ''} · ${detail.employee?.designation || ''}</p>
    <p>Payable days: ${detail.breakdown?.payableDays} / ${detail.breakdown?.workingDays}</p>
    <table><thead><tr><th>Component</th><th style="text-align:right">Amount</th></tr></thead><tbody>${components}</tbody></table>
    <p style="margin-top:16px"><strong>Gross:</strong> ₹${Number(detail.breakdown?.gross || 0).toFixed(2)}</p>
    <p><strong>Deductions:</strong> ₹${Number(detail.breakdown?.deductions || 0).toFixed(2)}</p>
    <p><strong>Net pay:</strong> ₹${Number(detail.netPay || 0).toFixed(2)}</p>
    </body></html>`)
  w.document.close()
  w.focus()
  w.print()
}
</script>
