<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Employees"
        description="Hire, edit access, and keep the directory current."
      >
        <template #actions>
          <Button
            v-if="canHire"
            variant="solid"
            label="New employee"
            icon-left="lucide-plus"
            @click="router.push({ name: 'EmployeeNew' })"
          />
        </template>
      </PageHeader>
    </template>

    <LoadingIndicator v-if="employees.loading" />
    <Card v-else-if="!rows.length" title="Employees">
      <p class="text-sm text-ink-gray-6">No employees yet.</p>
    </Card>
    <DataList
      v-else
      :items="rows"
      :columns="listColumns"
      :header-columns="headerColumns"
      empty-text="No employees yet."
      @row-click="openEmployee"
    >
      <template #row="{ item }">
        <ListCell>
          <span class="text-base font-medium text-ink-gray-8">{{ item.employee_code }}</span>
        </ListCell>
        <ListCell>
          <span class="truncate text-base text-ink-gray-8">{{ item.employee_name }}</span>
        </ListCell>
        <ListCell>
          <span class="truncate text-base text-ink-gray-7">{{ item.email }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.department || '—' }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.portal_role }}</span>
        </ListCell>
        <ListCell>
          <Badge :label="item.status" :theme="item.status === 'Active' ? 'green' : 'gray'" />
        </ListCell>
      </template>
    </DataList>
  </PageContent>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, createListResource, LoadingIndicator } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const session = useSessionStore()
const canHire = computed(() => session.hasRole('HR Admin', 'HR Manager', 'System Manager'))

const listColumns = [
  '7rem',
  'minmax(0,1fr)',
  'minmax(0,1.2fr)',
  '9rem',
  '10rem',
  '7rem',
]
const headerColumns = [
  { key: 'code', label: 'Code' },
  { key: 'name', label: 'Name' },
  { key: 'email', label: 'Email' },
  { key: 'department', label: 'Department' },
  { key: 'role', label: 'Role' },
  { key: 'status', label: 'Status' },
]

const employees = createListResource({
  doctype: 'HR Employee',
  fields: ['name', 'employee_code', 'employee_name', 'email', 'department', 'portal_role', 'status'],
  orderBy: 'modified desc',
  auto: true,
  pageLength: 100,
})

const rows = computed(() => employees.data || [])

function openEmployee(row) {
  router.push({ name: 'EmployeeDetail', params: { name: row.name } })
}
</script>
