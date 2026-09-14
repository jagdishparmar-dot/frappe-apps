<template>
  <Dropdown :options="menuItems">
    <template #default="{ open }">
      <button
        type="button"
        class="flex h-12 w-full items-center rounded-md py-2 duration-300 ease-in-out"
        :class="
          isCollapsed
            ? 'w-auto px-0'
            : open
              ? 'bg-surface-elevation-3 px-2 shadow-sm'
              : 'px-2 hover:bg-surface-gray-2'
        "
      >
        <div
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#1A3A6B] text-xs font-bold text-white"
        >
          HR
        </div>
        <div
          class="flex min-w-0 flex-1 flex-col truncate text-left duration-300 ease-in-out"
          :class="isCollapsed ? 'ml-0 w-0 overflow-hidden opacity-0' : 'ml-2 opacity-100'"
        >
          <div class="truncate text-base font-medium leading-none text-ink-gray-9">
            {{ companyName }}
          </div>
          <div class="mt-1 truncate text-sm leading-none text-ink-gray-7">
            {{ userName }}
          </div>
        </div>
        <span
          class="lucide-chevron-down size-4 shrink-0 text-ink-gray-5 duration-300 ease-in-out"
          :class="isCollapsed ? 'ml-0 w-0 overflow-hidden opacity-0' : 'ml-2 opacity-100'"
          aria-hidden="true"
        />
      </button>
    </template>
  </Dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Dropdown } from 'frappe-ui'
import { useSessionStore } from '@/stores/session'

const router = useRouter()

defineProps({
  isCollapsed: { type: Boolean, default: false },
})

const session = useSessionStore()

const companyName = computed(() => session.companyName || 'HR Portal')
const userName = computed(() => session.session?.full_name || session.user || 'User')

const menuItems = computed(() => [
  {
    group: 'Account',
    hideLabel: true,
    items: [
      {
        label: 'My HR',
        onClick: () => router.push({ name: 'Me' }),
      },
      {
        label: 'Log out',
        onClick: () => session.logout.submit(),
      },
    ],
  },
])
</script>
