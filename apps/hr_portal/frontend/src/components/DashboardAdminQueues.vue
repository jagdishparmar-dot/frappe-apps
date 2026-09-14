<template>
  <div class="grid gap-4 lg:grid-cols-3">
    <Card title="Regularizations" :subtitle="`${queues.regularizationsPending} pending`">
      <div v-if="!queues.regularizationItems.length" class="py-4 text-sm text-ink-gray-6">
        No pending regularizations.
      </div>
      <div v-else class="space-y-2">
        <RouterLink
          v-for="item in queues.regularizationItems"
          :key="item.id"
          :to="{ name: 'Attendance' }"
          class="block rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-outline-gray-2 hover:bg-surface-gray-1"
        >
          <p class="truncate text-sm font-medium">{{ item.employeeName }}</p>
          <p class="truncate text-xs text-ink-gray-6">
            {{ item.dateIso }} · {{ item.reason || 'No reason' }}
          </p>
        </RouterLink>
      </div>
    </Card>

    <Card title="Shift changes" :subtitle="`${queues.shiftChangesPending} pending`">
      <div v-if="!queues.shiftChangeItems.length" class="py-4 text-sm text-ink-gray-6">
        No pending shift changes.
      </div>
      <div v-else class="space-y-2">
        <RouterLink
          v-for="item in queues.shiftChangeItems"
          :key="item.id"
          :to="{ name: 'Shifts' }"
          class="block rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-outline-gray-2 hover:bg-surface-gray-1"
        >
          <p class="truncate text-sm font-medium">{{ item.employeeName }}</p>
          <p class="truncate text-xs text-ink-gray-6">
            {{ item.dateIso }} · {{ item.currentShiftLabel }} → {{ item.requestedShiftLabel }}
          </p>
        </RouterLink>
      </div>
    </Card>

    <Card title="Leave queue" :subtitle="`${leavePending} pending`">
      <div v-if="!leaveItems.length" class="py-4 text-sm text-ink-gray-6">
        No pending leave requests.
      </div>
      <div v-else class="space-y-2">
        <RouterLink
          v-for="item in leaveItems"
          :key="item.id"
          :to="{ name: 'Leave' }"
          class="block rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-outline-gray-2 hover:bg-surface-gray-1"
        >
          <p class="truncate text-sm font-medium">{{ item.employeeName }}</p>
          <p class="truncate text-xs text-ink-gray-6">
            {{ item.leaveTypeName }} · {{ item.days }}d · {{ item.fromDate }}
            <span v-if="item.toDate !== item.fromDate">→ {{ item.toDate }}</span>
          </p>
        </RouterLink>
      </div>
    </Card>
  </div>
</template>

<script setup>
defineProps({
  queues: { type: Object, required: true },
  leavePending: { type: Number, default: 0 },
  leaveItems: { type: Array, default: () => [] },
})
</script>
