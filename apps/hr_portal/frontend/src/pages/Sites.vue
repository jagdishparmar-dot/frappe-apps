<template>
  <PageContent>
    <template #header>
      <PageHeader
        title="Sites"
        description="Offices and client locations used for geofenced attendance."
      />
    </template>

    <Card :title="form.name ? 'Edit site' : 'New site'" class="max-w-3xl">
      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <FormControl v-model="form.site_name" label="Name" required class="sm:col-span-2" />
        <FormControl v-model.number="form.latitude" label="Latitude" type="number" step="0.000001" required />
        <FormControl v-model.number="form.longitude" label="Longitude" type="number" step="0.000001" required />
        <FormControl v-model.number="form.radius_meters" label="Radius (meters)" type="number" min="20" required />
        <FormControl v-model="form.status" label="Status" type="select" :options="statusOptions" />
        <FormControl v-model="form.address" label="Address" class="sm:col-span-2" />
        <FormAlerts :error="error" class="sm:col-span-2" />
        <div class="sm:col-span-2 flex gap-2">
          <Button type="submit" variant="solid" :loading="pending">Save site</Button>
          <Button v-if="form.name" variant="subtle" type="button" @click="resetForm">Clear</Button>
        </div>
      </form>
    </Card>

    <Card
      title="Live presence"
      :subtitle="`${live.totalCheckedIn} checked in · updated ${liveUpdated}`"
      class="mt-8"
    >
      <template #actions>
        <Button variant="outline" size="sm" @click="refreshLive">Refresh</Button>
      </template>
      <DataList
        :items="live.checkedIn"
        :columns="liveColumns"
        :header-columns="liveHeaders"
        empty-text="No one is currently punched in."
        row-class=""
      >
        <template #row="{ item }">
          <ListCell>
            <span class="truncate text-base text-ink-gray-8">{{ item.employeeName }}</span>
          </ListCell>
          <ListCell>
            <span class="truncate text-base text-ink-gray-7">{{ item.siteName }}</span>
          </ListCell>
          <ListCell>
            <span class="text-base text-ink-gray-7">{{ item.clockInTime }}</span>
          </ListCell>
          <ListCell>
            <Badge :label="item.status" :theme="item.status === 'Active' ? 'green' : 'gray'" />
          </ListCell>
        </template>
      </DataList>
    </Card>

    <DataList
      class="mt-6"
      :items="sites.data || []"
      :columns="siteColumns"
      :header-columns="siteHeaders"
      empty-text="No sites yet."
      @row-click="edit"
    >
      <template #row="{ item }">
        <ListCell>
          <span class="truncate text-base text-ink-gray-8">{{ item.site_name }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.latitude }}, {{ item.longitude }}</span>
        </ListCell>
        <ListCell>
          <span class="text-base text-ink-gray-7">{{ item.radius_meters }} m</span>
        </ListCell>
        <ListCell>
          <Badge :label="item.status" :theme="item.status === 'Active' ? 'green' : 'gray'" />
        </ListCell>
      </template>
    </DataList>
  </PageContent>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { Badge, Button, call, createListResource, FormControl } from 'frappe-ui'
import { ListCell } from 'frappe-ui/list'
import DataList from '@/components/DataList.vue'
import FormAlerts from '@/components/FormAlerts.vue'
import PageContent from '@/components/PageContent.vue'
import PageHeader from '@/components/PageHeader.vue'
import { apiError } from '@/lib/error'
import { selectOptions } from '@/lib/form'

const pending = ref(false)
const error = ref('')
const live = ref({ checkedIn: [], totalCheckedIn: 0, fetchedAt: '' })
let liveTimer = null

const statusOptions = selectOptions(['Active', 'Inactive'])
const siteColumns = ['minmax(0,1fr)', '12rem', '7rem', '7rem']
const siteHeaders = [
  { key: 'name', label: 'Name' },
  { key: 'coords', label: 'Lat / Long' },
  { key: 'radius', label: 'Radius' },
  { key: 'status', label: 'Status' },
]
const liveColumns = ['minmax(0,1fr)', 'minmax(0,1fr)', '8rem', '7rem']
const liveHeaders = [
  { key: 'employee', label: 'Employee' },
  { key: 'site', label: 'Site' },
  { key: 'in', label: 'In' },
  { key: 'status', label: 'Status' },
]

const liveUpdated = computed(() => {
  if (!live.value.fetchedAt) return '—'
  return new Date(live.value.fetchedAt).toLocaleTimeString()
})

async function refreshLive() {
  try {
    const data = await call('hr_portal.api.sites.get_live_presence')
    live.value = data
  } catch {
    /* HR roles only */
  }
}

const form = reactive({
  name: '',
  site_name: '',
  latitude: 19.076,
  longitude: 72.8777,
  radius_meters: 300,
  address: '',
  status: 'Active',
})

const sites = createListResource({
  doctype: 'HR Site',
  fields: ['name', 'site_name', 'latitude', 'longitude', 'radius_meters', 'address', 'status'],
  orderBy: 'site_name',
  auto: true,
  pageLength: 100,
})

function edit(row) {
  Object.assign(form, row)
}

function resetForm() {
  form.name = ''
  form.site_name = ''
  form.address = ''
  form.status = 'Active'
}

async function save() {
  error.value = ''
  pending.value = true
  try {
    await call('hr_portal.api.masters.save_site', { ...form })
    resetForm()
    sites.reload()
  } catch (e) {
    error.value = apiError(e, 'Unable to save site')
  } finally {
    pending.value = false
  }
}

onMounted(() => {
  refreshLive()
  liveTimer = window.setInterval(refreshLive, 60000)
})

onUnmounted(() => {
  if (liveTimer) window.clearInterval(liveTimer)
})
</script>
