<template>
  <Sidebar v-model:collapsed="sidebarCollapsed" width="15rem" class="border-r">
    <SidebarHeader
      :title="companyName"
      :subtitle="userName"
      :menu-items="headerMenuItems"
    />

    <ScrollArea class="min-h-0 flex-1" viewport-class="px-2 pt-0.5 pb-10">
      <div v-for="group in navGroups" :key="group.label" class="mb-3">
        <div class="flex h-7 items-center">
          <SidebarLabel>{{ group.label }}</SidebarLabel>
        </div>
        <nav class="mt-0.5 space-y-0.5">
          <SidebarItem
            v-for="item in group.items"
            :key="item.routeName"
            :to="item.to"
            :active="isNavItemActive(item, route.name)"
          >
            <template #prefix>
              <span :class="item.icon" class="size-4" aria-hidden="true" />
            </template>
            <span class="flex-1 truncate text-sm">{{ item.label }}</span>
          </SidebarItem>
        </nav>
      </div>
    </ScrollArea>

    <div class="px-2 pb-2">
      <SidebarCollapseToggle />
    </div>
  </Sidebar>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import {
  ScrollArea,
  Sidebar,
  SidebarCollapseToggle,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
} from 'frappe-ui'
import { groupsForRoles, isNavItemActive } from '@/nav'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const sidebarCollapsed = useStorage('hr-sidebar-collapsed', false)

const navGroups = computed(() => groupsForRoles(session.roles))
const companyName = computed(() => session.companyName || 'HR Portal')
const userName = computed(() => session.session?.full_name || session.user || 'User')

const headerMenuItems = computed(() => {
  const items = [
    {
      label: 'My HR',
      icon: 'lucide-user',
      onClick: () => router.push({ name: 'Me' }),
    },
  ]
  if (session.hasRole('HR Admin', 'System Manager')) {
    items.unshift({
      label: 'Settings',
      icon: 'lucide-settings-2',
      onClick: () => router.push({ name: 'Settings' }),
    })
  }
  items.push({
    label: 'Log out',
    icon: 'lucide-log-out',
    onClick: () => session.logout.submit(),
  })
  return items
})
</script>
