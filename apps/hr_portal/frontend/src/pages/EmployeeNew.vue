<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="New employee"
        description="Creates a Frappe login and an HR Employee row. They must change password on first sign-in."
        :breadcrumbs="[
          { label: 'Employees', route: { name: 'Employees' } },
          { label: 'New employee' },
        ]"
      />
    </template>

    <div class="max-w-3xl">
      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="submit">
        <FormControl v-model="form.employee_name" label="Full name" required class="sm:col-span-2" />
        <FormControl v-model="form.email" label="Work email" type="email" required />
        <FormControl v-model="form.password" label="Temporary password" type="password" required />
        <FormControl v-model="form.phone" label="Phone" required />
        <FormControl
          v-model="form.portal_role"
          label="Portal role"
          type="select"
          :options="roleOptions"
          required
        />
        <FormControl
          v-model="form.employment_type"
          label="Employment type"
          type="select"
          :options="employmentTypeOptions"
          required
        />
        <FormControl
          v-if="form.employment_type === '3PL'"
          v-model="form.vendor"
          label="3PL vendor"
          type="select"
          :options="vendorOptions"
          required
        />
        <FormControl
          v-model="form.department"
          label="Department"
          type="select"
          :options="departmentOptions"
        />
        <FormControl
          v-model="form.designation"
          label="Designation"
          type="select"
          :options="designationOptions"
        />
        <FormControl
          v-model="form.attendance_policy"
          label="Attendance policy"
          type="select"
          :options="attendancePolicyOptions"
          required
        />
        <FormControl
          v-model="form.primary_site"
          label="Primary site"
          type="select"
          :options="siteOptions"
          :required="form.attendance_policy === 'geofenced'"
        />
        <FormControl
          v-model="form.default_shift"
          label="Shift"
          type="select"
          :options="shiftOptions"
          :required="(options.shifts || []).length > 0"
        />
        <FormControl
          v-model="form.reports_to"
          label="Reports to"
          type="select"
          :options="managerOptions"
          class="sm:col-span-2"
        />
        <FormAlerts :error="error" class="sm:col-span-2" />
        <div class="sm:col-span-2 flex gap-2">
          <Button type="submit" variant="solid" :loading="pending">Hire</Button>
          <Button variant="subtle" type="button" @click="router.push({ name: 'Employees' })">Cancel</Button>
        </div>
      </form>
    </div>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, call, FormControl } from 'frappe-ui'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError } from '@/lib/error'
import { selectOptions, selectOptionsFromRows } from '@/lib/form'

const router = useRouter()
const options = ref({})
const pending = ref(false)
const error = ref('')
const form = reactive({
  employee_name: '',
  email: '',
  password: '',
  phone: '',
  portal_role: 'HR Employee',
  employment_type: 'Permanent',
  vendor: '',
  department: '',
  designation: '',
  attendance_policy: 'geofenced',
  primary_site: '',
  default_shift: '',
  reports_to: '',
})

const roleOptions = computed(() => selectOptions(options.value.roles || []))
const employmentTypeOptions = computed(() => selectOptions(['Permanent', '3PL', 'Intern', 'Consultant']))
const vendorOptions = computed(() =>
  selectOptionsFromRows(options.value.vendors || [], 'vendor_name', 'name', { emptyLabel: 'Select vendor' }),
)
const departmentOptions = computed(() => selectOptions(options.value.departments || [], { emptyLabel: '—' }))
const designationOptions = computed(() => selectOptions(options.value.designations || [], { emptyLabel: '—' }))
const attendancePolicyOptions = [
  { label: 'Geofenced', value: 'geofenced' },
  { label: 'GPS logged', value: 'gps_logged' },
  { label: 'Manual', value: 'manual' },
]
const siteOptions = computed(() =>
  selectOptionsFromRows(options.value.sites || [], 'site_name', 'name', { emptyLabel: 'Select site' }),
)
const shiftOptions = computed(() =>
  (options.value.shifts || []).map((row) => ({
    label: `${row.shift_name} (${row.code})`,
    value: row.name,
  })),
)
const managerOptions = computed(() => {
  const rows = (options.value.managers || []).map((row) => ({
    label: `${row.employee_name} (${row.employee_code})`,
    value: row.name,
  }))
  return [{ label: '—', value: '' }, ...rows]
})

onMounted(async () => {
  options.value = await call('hr_portal.api.employees.get_hire_options')
})

async function submit() {
  error.value = ''
  pending.value = true
  try {
    const result = await call('hr_portal.api.employees.create_employee', { ...form })
    router.replace({ name: 'EmployeeDetail', params: { name: result.name } })
  } catch (e) {
    error.value = apiError(e, 'Unable to hire employee')
  } finally {
    pending.value = false
  }
}
</script>
