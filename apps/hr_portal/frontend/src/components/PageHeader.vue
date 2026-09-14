<template>
  <ShellPageHeader>
    <div class="flex min-w-0 flex-1 flex-col gap-0.5">
      <div class="flex min-w-0 items-center gap-2">
        <PageHeaderBackButton v-if="showBack" @click="router.back()" />
        <PageHeaderTitle>{{ title }}</PageHeaderTitle>
      </div>
      <p v-if="description" class="truncate text-sm text-ink-gray-6">{{ description }}</p>
      <nav v-if="breadcrumbs.length" class="flex flex-wrap items-center gap-1 text-sm text-ink-gray-6">
        <template v-for="(item, index) in breadcrumbs" :key="`${item.label}-${index}`">
          <RouterLink
            v-if="item.route"
            :to="item.route"
            class="hover:text-ink-gray-8"
          >
            {{ item.label }}
          </RouterLink>
          <span v-else>{{ item.label }}</span>
          <span v-if="index < breadcrumbs.length - 1" class="text-ink-gray-4">/</span>
        </template>
      </nav>
    </div>
    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </ShellPageHeader>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  PageHeader as ShellPageHeader,
  PageHeaderBackButton,
  PageHeaderTitle,
} from 'frappe-ui'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  breadcrumbs: { type: Array, default: () => [] },
  showBack: { type: Boolean, default: false },
})

const router = useRouter()
const breadcrumbs = computed(() => props.breadcrumbs || [])
</script>
