<template>
  <PageContent>
    <template #header>
      <PageHeader
        v-if="employee"
        :title="form.employee_name"
        :description="`${employee.employeeCode} · ${employee.email}`"
        :breadcrumbs="[
          { label: 'Employees', route: { name: 'Employees' } },
          { label: form.employee_name },
        ]"
      >
        <template #actions>
          <Button variant="subtle" @click="router.push({ name: 'Employees' })">Back</Button>
        </template>
      </PageHeader>
    </template>

    <div class="max-w-3xl">
      <LoadingIndicator v-if="loading" />
      <template v-else-if="employee">
        <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
          <FormControl v-model="form.employee_name" label="Full name" required class="sm:col-span-2" />
          <FormControl v-model="form.phone" label="Phone" />
          <FormControl
            v-model="form.portal_role"
            label="Portal role"
            type="select"
            :options="roleOptions"
          />
          <FormControl
            v-model="form.employment_type"
            label="Employment type"
            type="select"
            :options="employmentTypeOptions"
          />
          <FormControl
            v-if="form.employment_type === '3PL'"
            v-model="form.vendor"
            label="3PL vendor"
            type="select"
            :options="vendorOptions"
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
          />
          <FormControl
            v-model="form.primary_site"
            label="Primary site"
            type="select"
            :options="siteOptions"
          />
          <FormControl
            v-model="form.default_shift"
            label="Shift"
            type="select"
            :options="shiftOptions"
          />
          <FormControl
            v-model="form.status"
            label="Status"
            type="select"
            :options="statusOptions"
          />
          <FormAlerts :error="error" :success="saved ? 'Saved.' : ''" class="sm:col-span-2" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="solid" :loading="pending">Save</Button>
          </div>
        </form>

        <Card v-if="canManagePayroll" title="Salary structure" class="mt-10">
          <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="saveSalary">
            <FormControl v-model="salaryForm.effective_from" label="Effective from" type="date" required />
            <FormControl v-model.number="salaryForm.basic" label="Basic" type="number" min="0" step="0.01" />
            <FormControl v-model.number="salaryForm.hra" label="HRA" type="number" min="0" step="0.01" />
            <FormControl v-model.number="salaryForm.special_allowance" label="Special allowance" type="number" min="0" step="0.01" />
            <FormControl v-model.number="salaryForm.other_earnings" label="Other earnings" type="number" min="0" step="0.01" />
            <FormControl v-model.number="salaryForm.deductions" label="Deductions" type="number" min="0" step="0.01" />
            <p v-if="salaryForm.ctcMonthly" class="sm:col-span-2 text-sm text-ink-gray-6">
              CTC monthly: ₹{{ salaryForm.ctcMonthly.toLocaleString('en-IN') }}
            </p>
            <div class="sm:col-span-2">
              <Button type="submit" variant="subtle" :loading="salaryPending">Save salary structure</Button>
            </div>
          </form>
        </Card>

        <Card title="Reset password" class="mt-10">
          <form class="flex flex-wrap items-end gap-3" @submit.prevent="resetPassword">
            <FormControl v-model="newPassword" label="New password" type="password" minlength="8" required />
            <Button type="submit" variant="subtle" :loading="resetting">Reset</Button>
          </form>
        </Card>

        <Card title="Documents" class="mt-6">
          <form class="flex flex-wrap items-end gap-3" @submit.prevent="upload">
            <FormControl v-model="uploadForm.title" label="Title" required />
            <FormControl
              v-model="uploadForm.category"
              label="Category"
              type="select"
              :options="documentCategoryOptions"
            />
            <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" @change="onFile" />
            <Button type="submit" variant="subtle" :loading="uploading" :disabled="!file">Upload</Button>
          </form>
          <ul class="mt-4 space-y-2 text-sm">
            <li v-for="doc in documents" :key="doc.id" class="flex justify-between gap-3">
              <a :href="doc.previewUrl" class="text-ink-blue-2 hover:underline" target="_blank">{{ doc.title }}</a>
              <span class="text-ink-gray-5">{{ doc.category }}</span>
            </li>
            <li v-if="!documents.length" class="text-ink-gray-5">No documents yet.</li>
          </ul>
        </Card>
      </template>
    </div>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, call, FormControl, LoadingIndicator } from 'frappe-ui'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError, fileToBase64 } from '@/lib/error'
import { selectOptions, selectOptionsFromRows } from '@/lib/form'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const canManagePayroll = computed(() => session.hasRole('HR Admin', 'HR Payroll Admin', 'System Manager'))
const loading = ref(true)
const pending = ref(false)
const resetting = ref(false)
const uploading = ref(false)
const error = ref('')
const saved = ref(false)
const employee = ref(null)
const documents = ref([])
const options = ref({})
const newPassword = ref('')
const file = ref(null)
const uploadForm = reactive({ title: '', category: 'identity' })
const salaryPending = ref(false)
const salaryForm = reactive({
  effective_from: new Date().toISOString().slice(0, 10),
  basic: 0,
  hra: 0,
  special_allowance: 0,
  other_earnings: 0,
  deductions: 0,
  ctcMonthly: 0,
})
const form = reactive({
  employee_name: '',
  phone: '',
  portal_role: 'HR Employee',
  employment_type: 'Permanent',
  vendor: '',
  department: '',
  designation: '',
  attendance_policy: 'geofenced',
  primary_site: '',
  default_shift: '',
  status: 'Active',
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
  selectOptionsFromRows(options.value.shifts || [], 'shift_name', 'name', { emptyLabel: 'Select shift' }),
)
const statusOptions = selectOptions(['Active', 'Inactive', 'Invited'])
const documentCategoryOptions = [
  { label: 'Profile picture', value: 'profile_picture' },
  { label: 'Identity', value: 'identity' },
  { label: 'Compliance', value: 'compliance' },
  { label: 'Employment', value: 'employment' },
]

onMounted(load)

async function load() {
  loading.value = true
  try {
    const [detail, hireOptions, docs] = await Promise.all([
      call('hr_portal.api.employees.get_employee', { name: route.params.name }),
      call('hr_portal.api.employees.get_hire_options'),
      call('hr_portal.api.documents.list_employee_documents', { employee: route.params.name }),
    ])
    employee.value = detail.employee
    options.value = hireOptions
    documents.value = docs.documents || []
    const emp = detail.employee
    form.employee_name = emp.name
    form.phone = emp.phone
    form.portal_role = emp.role
    form.employment_type = emp.employmentType || 'Permanent'
    form.vendor = emp.vendorId
    form.department = emp.department
    form.designation = emp.designation
    form.attendance_policy = emp.attendancePolicy
    form.primary_site = emp.primarySiteId
    form.default_shift = emp.shiftId
    form.status = (emp.status || 'active').replace(/^./, (c) => c.toUpperCase())
    if (canManagePayroll.value) {
      const structure = await call('hr_portal.api.payroll.get_salary_structure', { employee: route.params.name }).catch(() => null)
      if (structure) {
        salaryForm.effective_from = structure.effectiveFrom
        salaryForm.basic = structure.basic
        salaryForm.hra = structure.hra
        salaryForm.special_allowance = structure.specialAllowance
        salaryForm.other_earnings = structure.otherEarnings
        salaryForm.deductions = structure.deductions
        salaryForm.ctcMonthly = structure.ctcMonthly
      }
    }
  } finally {
    loading.value = false
  }
}

watch(
  () => [salaryForm.basic, salaryForm.hra, salaryForm.special_allowance, salaryForm.other_earnings, salaryForm.deductions],
  () => {
    salaryForm.ctcMonthly =
      Number(salaryForm.basic || 0) +
      Number(salaryForm.hra || 0) +
      Number(salaryForm.special_allowance || 0) +
      Number(salaryForm.other_earnings || 0) -
      Number(salaryForm.deductions || 0)
  },
)

async function saveSalary() {
  salaryPending.value = true
  try {
    await call('hr_portal.api.payroll.save_salary_structure', {
      employee: route.params.name,
      ...salaryForm,
    })
    saved.value = true
  } catch (e) {
    error.value = apiError(e, 'Unable to save salary structure')
  } finally {
    salaryPending.value = false
  }
}

async function save() {
  error.value = ''
  saved.value = false
  pending.value = true
  try {
    await call('hr_portal.api.employees.update_employee', { name: route.params.name, ...form })
    saved.value = true
  } catch (e) {
    error.value = apiError(e, 'Unable to save')
  } finally {
    pending.value = false
  }
}

async function resetPassword() {
  resetting.value = true
  try {
    await call('hr_portal.api.employees.reset_employee_password', {
      name: route.params.name,
      new_password: newPassword.value,
    })
    newPassword.value = ''
    saved.value = true
  } catch (e) {
    error.value = apiError(e, 'Unable to reset password')
  } finally {
    resetting.value = false
  }
}

function onFile(event) {
  file.value = event.target.files?.[0] || null
  if (file.value && !uploadForm.title) {
    uploadForm.title = file.value.name
  }
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const data_base64 = await fileToBase64(file.value)
    await call('hr_portal.api.documents.upload_document', {
      employee: route.params.name,
      category: uploadForm.category,
      title: uploadForm.title,
      file_name: file.value.name,
      mime_type: file.value.type,
      data_base64,
    })
    const docs = await call('hr_portal.api.documents.list_employee_documents', { employee: route.params.name })
    documents.value = docs.documents || []
    file.value = null
  } catch (e) {
    error.value = apiError(e, 'Unable to upload')
  } finally {
    uploading.value = false
  }
}
</script>
