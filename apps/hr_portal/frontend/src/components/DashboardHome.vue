<template>
  <div class="flex flex-col gap-5">
    <section
      class="relative overflow-hidden rounded-2xl border border-outline-gray-2 bg-gradient-to-br from-indigo-50 via-surface-white to-sky-50/70 px-5 py-5 shadow-sm sm:px-6"
    >
      <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="text-xs font-medium uppercase tracking-[0.18em] text-indigo-700/80">
            {{ companyName }}
          </p>
          <h2 class="mt-1 text-2xl font-semibold tracking-tight text-ink-gray-9 sm:text-3xl">
            Good day, {{ firstName }}
          </h2>
          <p class="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
            <span class="lucide-calendar-days size-4" aria-hidden="true" />
            {{ formattedDate }}
            <span class="text-outline-gray-3">·</span>
            <span>{{ roleLabel }}</span>
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button v-if="isAdmin" variant="solid" @click="go('Attendance')">
            Review attendance
          </Button>
          <Button variant="outline" @click="go('Employees')">Employees</Button>
          <Button variant="outline" @click="go('Attendance')">Attendance</Button>
          <Button v-if="isAdmin" variant="outline" @click="go('Shifts')">Shift roster</Button>
          <Button v-else variant="outline" @click="go('Leave')">Leave</Button>
        </div>
      </div>
    </section>

    <DashboardAdminQueues
      v-if="isAdmin && snapshot.adminQueues"
      :queues="snapshot.adminQueues"
      :leave-pending="snapshot.leave.pending"
      :leave-items="snapshot.leave.pendingItems"
    />

    <div v-if="isAdmin" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <RouterLink
        v-for="stat in adminStats"
        :key="stat.title"
        :to="stat.to"
        class="block rounded-xl transition-opacity hover:opacity-90"
        :class="stat.highlight ? 'ring-1 ring-amber-300/70' : ''"
      >
        <NumberCard
          :title="stat.title"
          :value="stat.value"
          :delta-caption="stat.caption"
        />
      </RouterLink>
    </div>

    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      <RouterLink
        v-for="stat in kpiStats"
        :key="stat.title"
        :to="stat.to"
        class="block rounded-xl transition-opacity hover:opacity-90"
      >
        <NumberCard
          :title="stat.title"
          :value="stat.value"
          :delta-caption="stat.caption"
        />
      </RouterLink>
    </div>

    <div class="grid gap-4 xl:grid-cols-12">
      <div class="space-y-4 xl:col-span-8">
        <Card
          title="Today's attendance mix"
          :subtitle="`${snapshot.attendance.marked} of ${snapshot.employees.active} employees marked · ${snapshot.today}`"
        >
          <div v-if="mixSegments.length" class="space-y-3">
            <div class="flex h-2.5 overflow-hidden rounded-full bg-surface-gray-2">
              <div
                v-for="segment in mixSegments"
                :key="segment.key"
                class="h-full transition-all"
                :class="segment.className"
                :style="{ width: `${(segment.value / mixTotal) * 100}%` }"
                :title="`${segment.label}: ${segment.value}`"
              />
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-6">
              <span v-for="segment in mixSegments" :key="`${segment.key}-legend`" class="inline-flex items-center gap-1.5">
                <span class="size-2 rounded-full" :class="segment.className" />
                {{ segment.label }} {{ segment.value }}
              </span>
            </div>
          </div>
          <div v-if="mixChartData.length" class="mt-4 h-64">
            <DonutChart
              :data="mixChartData"
              category="label"
              value="count"
              center-label="marked"
              title="Status breakdown"
              :subtitle="`${snapshot.attendance.marked} employees today`"
            />
          </div>
          <p v-else class="py-6 text-center text-sm text-ink-gray-6">
            No attendance marked yet today.
          </p>
        </Card>

        <Card title="On duty now" :subtitle="`${snapshot.onDutyNow.length} open punches`">
          <div v-if="!snapshot.onDutyNow.length" class="py-6 text-center text-sm text-ink-gray-6">
            No one is currently punched in.
          </div>
          <div v-else class="max-h-64 space-y-1 overflow-y-auto">
            <RouterLink
              v-for="row in snapshot.onDutyNow"
              :key="`${row.employeeId}-${row.clockInTime}`"
              :to="{ name: 'EmployeeDetail', params: { name: row.employeeId } }"
              class="flex items-center gap-3 rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-outline-gray-2 hover:bg-surface-gray-1"
            >
              <div class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-indigo-1 text-xs font-semibold text-ink-indigo-3">
                {{ initials(row.employeeName) }}
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium">{{ row.employeeName }}</p>
                <p class="truncate text-xs text-ink-gray-6">
                  {{ row.siteName }} · in {{ row.clockInTime }}
                </p>
              </div>
              <Badge :label="row.status" :theme="statusTheme(row.status)" />
            </RouterLink>
          </div>
        </Card>

        <Card title="Recent punches" subtitle="Latest activity across the company">
          <template #actions>
            <Button variant="outline" size="sm" @click="go('Attendance')">All attendance</Button>
          </template>
          <DataList
            :items="snapshot.recent"
            :columns="recentColumns"
            :header-columns="recentHeaders"
            empty-text="No punches yet. Assign sites and use mobile check-in."
            row-class=""
            @row-click="openEmployeeFromRecent"
          >
            <template #row="{ item }">
              <ListCell>
                <span class="truncate text-base font-medium text-ink-gray-8">{{ item.employeeName }}</span>
              </ListCell>
              <ListCell>
                <span class="text-base text-ink-gray-7">{{ item.dateIso }}</span>
              </ListCell>
              <ListCell>
                <span class="text-base text-ink-gray-7">{{ item.clockInTime || '—' }}</span>
              </ListCell>
              <ListCell>
                <span class="text-base text-ink-gray-7">{{ item.clockOutTime || '—' }}</span>
              </ListCell>
              <ListCell>
                <Badge :label="item.status" :theme="statusTheme(item.status)" />
              </ListCell>
              <ListCell>
                <span class="truncate text-base text-ink-gray-7">{{ item.locationName || '—' }}</span>
              </ListCell>
            </template>
          </DataList>
        </Card>
      </div>

      <div class="space-y-4 xl:col-span-4">
        <Card v-if="isAdmin" title="Needs attention" :subtitle="attentionSubtitle">
          <div class="space-y-1">
            <RouterLink
              v-for="row in attentionRows"
              :key="row.label"
              :to="row.to"
              class="flex items-center justify-between rounded-lg border border-transparent px-2 py-2 text-sm transition-colors hover:border-outline-gray-2 hover:bg-surface-gray-1"
            >
              <span class="text-ink-gray-6">{{ row.label }}</span>
              <span class="font-semibold tabular-nums" :class="row.valueClass">{{ row.value }}</span>
            </RouterLink>
          </div>
        </Card>

        <Card v-else title="Pending leave" subtitle="Awaiting approval">
          <template #actions>
            <Button variant="ghost" size="sm" @click="go('Leave')">View</Button>
          </template>
          <div v-if="!snapshot.leave.pendingItems.length" class="py-6 text-center text-sm text-ink-gray-6">
            No pending leave requests.
          </div>
          <div v-else class="max-h-64 space-y-2 overflow-y-auto">
            <div
              v-for="item in snapshot.leave.pendingItems"
              :key="item.id"
              class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5"
            >
              <p class="truncate text-sm font-medium">{{ item.employeeName }}</p>
              <p class="text-xs text-ink-gray-6">
                {{ item.leaveTypeName }} · {{ item.days }}d · {{ item.fromDate }}
                <span v-if="item.toDate !== item.fromDate">→ {{ item.toDate }}</span>
              </p>
            </div>
          </div>
        </Card>

        <Card title="Workforce" subtitle="Active employee breakdown">
          <div class="grid grid-cols-3 gap-2 text-center">
            <div
              v-for="mini in workforceMini"
              :key="mini.label"
              class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-2 py-2"
            >
              <p class="text-xs text-ink-gray-6">{{ mini.label }}</p>
              <p class="text-lg font-bold tabular-nums">{{ mini.value }}</p>
            </div>
          </div>
          <div v-if="typeEntries.length" class="mt-4 space-y-2 border-t border-outline-gray-2 pt-3">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-6">
              Employment type
            </p>
            <div v-for="[type, count] in typeEntries" :key="type" class="space-y-1">
              <div class="flex justify-between text-xs">
                <span>{{ type }}</span>
                <span class="font-medium tabular-nums">{{ count }}</span>
              </div>
              <div class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2">
                <div
                  class="h-full rounded-full bg-indigo-500/80"
                  :style="{ width: `${(count / maxType) * 100}%` }"
                />
              </div>
            </div>
          </div>
        </Card>

        <Card
          title="On leave today"
          :subtitle="`${snapshot.leave.onLeaveTodayItems.length} approved`"
        >
          <div v-if="!snapshot.leave.onLeaveTodayItems.length" class="py-4 text-center text-sm text-ink-gray-6">
            No approved leave for today.
          </div>
          <div v-else class="max-h-56 space-y-2 overflow-y-auto">
            <div
              v-for="item in snapshot.leave.onLeaveTodayItems"
              :key="item.id"
              class="flex items-start gap-2 rounded-lg px-1 py-1.5"
            >
              <span class="lucide-palmtree mt-0.5 size-3.5 shrink-0 text-sky-500" aria-hidden="true" />
              <div class="min-w-0">
                <p class="truncate text-sm font-medium">{{ item.employeeName }}</p>
                <p class="text-xs text-ink-gray-6">
                  {{ item.leaveTypeName }}
                  <span v-if="item.toDate !== item.fromDate">· until {{ item.toDate }}</span>
                  <span v-else>· today</span>
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { DonutChart, NumberCard } from 'frappe-ui/charts'
import { ListCell } from 'frappe-ui/list'
import DashboardAdminQueues from '@/components/DashboardAdminQueues.vue'
import DataList from '@/components/DataList.vue'
import { formatDashboardDate, primaryRoleLabel, statusTheme } from '@/lib/dashboard'

const props = defineProps({
  snapshot: { type: Object, required: true },
  companyName: { type: String, default: 'HR' },
  userName: { type: String, default: '' },
  roles: { type: Array, default: () => [] },
  isAdmin: { type: Boolean, default: false },
})

const router = useRouter()

const firstName = computed(() => (props.userName || 'there').split(' ')[0])
const formattedDate = computed(() => formatDashboardDate(props.snapshot.today))
const roleLabel = computed(() => primaryRoleLabel(props.roles))

const shiftChangesPending = computed(
  () => props.snapshot.adminQueues?.shiftChangesPending ?? 0,
)

const actionBacklog = computed(
  () =>
    props.snapshot.leave.pending +
    props.snapshot.regularizationsPending +
    shiftChangesPending.value,
)

const attentionSubtitle = computed(() =>
  actionBacklog.value > 0
    ? `${actionBacklog.value} approval${actionBacklog.value === 1 ? '' : 's'} in queue`
    : 'Operational follow-ups for today',
)

function route(name) {
  return { name }
}

const adminStats = computed(() => [
  {
    title: 'Regularize',
    value: props.snapshot.regularizationsPending,
    caption: 'Pending review',
    to: route('Attendance'),
    highlight: props.snapshot.regularizationsPending > 0,
  },
  {
    title: 'Shift changes',
    value: shiftChangesPending.value,
    caption: 'Pending review',
    to: route('Shifts'),
    highlight: shiftChangesPending.value > 0,
  },
  {
    title: 'Leave queue',
    value: props.snapshot.leave.pending,
    caption: 'Pending approval',
    to: route('Leave'),
    highlight: props.snapshot.leave.pending > 0,
  },
  {
    title: 'Not marked',
    value: props.snapshot.attendance.unmarked,
    caption: 'Today',
    to: route('Attendance'),
    highlight: props.snapshot.attendance.unmarked > 0,
  },
])

const kpiStats = computed(() => [
  {
    title: 'Present',
    value: props.snapshot.attendance.present,
    caption: 'On time',
    to: route('Attendance'),
  },
  {
    title: 'Late',
    value: props.snapshot.attendance.late,
    caption: 'Today',
    to: route('Attendance'),
  },
  {
    title: 'Absent',
    value: props.snapshot.attendance.absent,
    caption: 'Marked',
    to: route('Attendance'),
  },
  {
    title: 'On leave',
    value: props.snapshot.leave.onLeaveToday,
    caption: 'Approved today',
    to: route('Leave'),
  },
  {
    title: 'Open shifts',
    value: props.snapshot.attendance.openShifts,
    caption: 'Still in',
    to: route('Attendance'),
  },
  {
    title: 'Active',
    value: props.snapshot.employees.active,
    caption: 'Headcount',
    to: route('Employees'),
  },
])

const mixTotal = computed(() => Math.max(props.snapshot.employees.active, 1))

const mixSegments = computed(() => {
  const { attendance } = props.snapshot
  return [
    { key: 'present', label: 'Present', value: attendance.present, className: 'bg-emerald-500' },
    { key: 'late', label: 'Late', value: attendance.late, className: 'bg-amber-500' },
    { key: 'halfDay', label: 'Half day', value: attendance.halfDay, className: 'bg-indigo-500' },
    { key: 'onLeave', label: 'Leave', value: attendance.onLeave, className: 'bg-sky-500' },
    { key: 'absent', label: 'Absent', value: attendance.absent, className: 'bg-rose-500' },
    {
      key: 'unmarked',
      label: 'Not marked',
      value: attendance.unmarked,
      className: 'bg-slate-400/60',
    },
  ].filter((segment) => segment.value > 0)
})

const mixChartData = computed(() =>
  mixSegments.value.map((segment) => ({
    label: segment.label,
    count: segment.value,
  })),
)

const typeEntries = computed(() =>
  Object.entries(props.snapshot.employees.byType || {}).sort((a, b) => b[1] - a[1]),
)

const maxType = computed(() => typeEntries.value[0]?.[1] || 1)

const workforceMini = computed(() => [
  { label: 'Active', value: props.snapshot.employees.active },
  { label: 'Inactive', value: props.snapshot.employees.inactive },
  { label: 'Invited', value: props.snapshot.employees.invited },
])

const attentionRows = computed(() => {
  const { attendance, leave, regularizationsPending } = props.snapshot
  return [
    {
      label: 'Pending regularizations',
      value: regularizationsPending,
      to: route('Attendance'),
      valueClass: regularizationsPending > 0 ? 'text-rose-700' : 'text-ink-gray-6',
    },
    {
      label: 'Pending shift changes',
      value: shiftChangesPending.value,
      to: route('Shifts'),
      valueClass: shiftChangesPending.value > 0 ? 'text-amber-700' : 'text-ink-gray-6',
    },
    {
      label: 'Pending leave',
      value: leave.pending,
      to: route('Leave'),
      valueClass: leave.pending > 0 ? 'text-sky-700' : 'text-ink-gray-6',
    },
    {
      label: 'Unmarked attendance',
      value: attendance.unmarked,
      to: route('Attendance'),
      valueClass: attendance.unmarked > 0 ? 'text-amber-700' : 'text-ink-gray-6',
    },
    {
      label: 'Late arrivals',
      value: attendance.late,
      to: route('Attendance'),
      valueClass: attendance.late > 0 ? 'text-amber-700' : 'text-ink-gray-6',
    },
  ]
})

const recentColumns = [
  'minmax(0,1fr)',
  '8rem',
  '6rem',
  '6rem',
  '8rem',
  'minmax(0,1fr)',
]
const recentHeaders = [
  { key: 'employee', label: 'Employee' },
  { key: 'date', label: 'Date' },
  { key: 'in', label: 'In' },
  { key: 'out', label: 'Out' },
  { key: 'status', label: 'Status' },
  { key: 'site', label: 'Site' },
]

function go(name) {
  router.push({ name })
}

function initials(name) {
  return String(name || 'E')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('')
}

function openEmployeeFromRecent(item) {
  if (item?.employeeId) {
    router.push({ name: 'EmployeeDetail', params: { name: item.employeeId } })
  }
}
</script>
