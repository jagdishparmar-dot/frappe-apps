<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="My HR"
        description="Your profile, documents, and payslips."
      />
    </template>

    <div class="max-w-3xl">
      <LoadingIndicator v-if="loading" />
      <template v-else-if="profile">
        <Card title="Profile">
          <dl class="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt class="text-ink-gray-5">Name</dt>
              <dd>{{ profile.employee.name }}</dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">Code</dt>
              <dd>{{ profile.employee.employeeCode }}</dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">Department</dt>
              <dd>{{ profile.employee.department || '—' }}</dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">Role</dt>
              <dd>{{ profile.employee.role }}</dd>
            </div>
          </dl>
        </Card>

        <form class="mt-6 grid gap-4 sm:grid-cols-2" @submit.prevent="save">
          <FormControl v-model="form.phone" label="Phone" />
          <FormControl v-model="form.emergencyContactName" label="Emergency contact" />
          <FormControl v-model="form.emergencyContactPhone" label="Emergency phone" />
          <FormControl v-model="form.currentCity" label="City" />
          <FormControl v-model="form.currentAddressLine1" label="Address" class="sm:col-span-2" />
          <FormAlerts :error="error" :success="saved ? 'Saved.' : ''" class="sm:col-span-2" />
          <div class="sm:col-span-2">
            <Button type="submit" variant="solid" :loading="pending">Save profile</Button>
          </div>
        </form>

        <Card title="Payslips" class="mt-8">
          <ul class="space-y-2 text-sm">
            <li v-for="slip in payslips" :key="slip.id" class="flex justify-between gap-3">
              <span>{{ slip.month }}</span>
              <span class="font-medium tabular-nums">₹{{ Number(slip.netPay || 0).toLocaleString('en-IN') }}</span>
            </li>
            <li v-if="!payslips.length" class="text-ink-gray-6">No payslips yet.</li>
          </ul>
        </Card>

        <Card title="Documents" class="mt-8">
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
            <li v-for="doc in profile.documents || []" :key="doc.id">
              <a :href="doc.previewUrl" class="text-ink-blue-2 hover:underline" target="_blank">{{ doc.title }}</a>
              <span class="ml-2 text-ink-gray-5">{{ doc.category }}</span>
            </li>
          </ul>
        </Card>
      </template>
    </div>
  </PageContent>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Button, call, FormControl, LoadingIndicator } from 'frappe-ui'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError, fileToBase64 } from '@/lib/error'

const loading = ref(true)
const pending = ref(false)
const uploading = ref(false)
const error = ref('')
const saved = ref(false)
const profile = ref(null)
const payslips = ref([])
const file = ref(null)
const form = reactive({
  phone: '',
  emergencyContactName: '',
  emergencyContactPhone: '',
  currentCity: '',
  currentAddressLine1: '',
})
const uploadForm = reactive({ title: '', category: 'identity' })

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
    const [data, slips] = await Promise.all([
      call('hr_portal.api.profile.get_profile'),
      call('hr_portal.api.payroll.list_my_payslips').catch(() => []),
    ])
    profile.value = data
    payslips.value = slips || []
    form.phone = data.employee.phone
    form.emergencyContactName = data.employee.emergencyContactName
    form.emergencyContactPhone = data.employee.emergencyContactPhone
    form.currentCity = data.employee.currentCity
    form.currentAddressLine1 = data.employee.currentAddressLine1
  } catch (e) {
    error.value = apiError(e, 'Unable to load profile')
  } finally {
    loading.value = false
  }
}

async function save() {
  error.value = ''
  saved.value = false
  pending.value = true
  try {
    profile.value = await call('hr_portal.api.profile.update_profile', { ...form })
    saved.value = true
  } catch (e) {
    error.value = apiError(e, 'Unable to save profile')
  } finally {
    pending.value = false
  }
}

function onFile(event) {
  file.value = event.target.files?.[0] || null
  if (file.value && !uploadForm.title) uploadForm.title = file.value.name
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const data_base64 = await fileToBase64(file.value)
    await call('hr_portal.api.documents.upload_document', {
      category: uploadForm.category,
      title: uploadForm.title,
      file_name: file.value.name,
      mime_type: file.value.type,
      data_base64,
    })
    await load()
  } catch (e) {
    error.value = apiError(e, 'Unable to upload')
  } finally {
    uploading.value = false
  }
}
</script>
