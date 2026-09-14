<template>
  <List
    class="w-full list-row-px-3"
    :class="listClass"
    :columns="columns"
    :row-height="rowHeight"
    :selectable="selectable"
    :selection="selection"
    @update:selection="$emit('update:selection', $event)"
  >
    <ListHeader v-if="!hideHeader">
      <slot name="header">
        <ListHeaderCell
          v-for="column in headerColumns"
          :key="column.key"
          :class="column.align === 'end' ? 'justify-end' : ''"
        >
          {{ column.label }}
        </ListHeaderCell>
      </slot>
    </ListHeader>
    <ListRows :items="items" v-slot="{ item, value }">
      <ListRow
        :value="value"
        :class="rowClass"
        @click="$emit('row-click', item)"
      >
        <slot name="row" :item="item" />
      </ListRow>
    </ListRows>
  </List>
  <p v-if="!items.length && emptyText" class="py-4 text-sm text-ink-gray-6">
    {{ emptyText }}
  </p>
</template>

<script setup>
import {
  List,
  ListCell,
  ListHeader,
  ListHeaderCell,
  ListRow,
  ListRows,
} from 'frappe-ui/list'

defineProps({
  items: { type: Array, default: () => [] },
  columns: { type: Array, required: true },
  headerColumns: { type: Array, default: () => [] },
  rowHeight: { type: Number, default: 40 },
  emptyText: { type: String, default: '' },
  hideHeader: { type: Boolean, default: false },
  listClass: { type: String, default: '' },
  rowClass: { type: String, default: 'cursor-pointer' },
  selectable: { type: Boolean, default: false },
  selection: { type: Array, default: () => [] },
})

defineEmits(['row-click', 'update:selection'])
</script>
