<script setup>
import { computed } from 'vue'
import { displaySectionItemValue, displayText } from '../domain/displayLabels.js'
import VisualizationTable from './VisualizationTable.vue'

const props = defineProps({
  section: { type: Object, required: true },
  selectable: { type: Boolean, default: true },
})

const emit = defineEmits(['select'])

const levelOrder = Object.freeze(['Minor', 'Moderate', 'Major', 'Extreme'])
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: true })

const rows = computed(() => {
  const items = Array.isArray(props.section.items) ? props.section.items : []
  const byName = new Map(items.map(item => [item.name, item]))
  const ordered = levelOrder.map(name => byName.get(name)).filter(Boolean)
  const remaining = items.filter(item => !levelOrder.includes(item.name))
  return [...ordered, ...remaining].map((item, index) => ({
    ...item,
    key: `${item.name || 'level'}-${index}`,
    label: displaySectionItemValue(item.name || '未分类', props.section),
    value: typeof item.value === 'number' && Number.isFinite(item.value) ? item.value : 0,
    levelIndex: levelOrder.indexOf(item.name),
  }))
})

const maxValue = computed(() => Math.max(...rows.value.map(row => Math.max(0, row.value)), 1))

function formatCount(value) {
  return number.format(value)
}

</script>

<template>
  <div class="risk-distribution-visual" :class="`risk-distribution-visual--${section.key}`">
    <div v-if="rows.length" class="risk-distribution-rows" role="list" :aria-label="`${displayText(section.title)}分层明细`">
      <div v-for="row in rows" :key="row.key" class="risk-distribution-row" role="listitem" :class="[`risk-level-${row.levelIndex}`, { 'is-high-level': row.levelIndex >= 2 }]">
        <div class="risk-distribution-row-label">
          <span class="risk-distribution-row-index" aria-hidden="true">{{ row.levelIndex >= 0 ? row.levelIndex + 1 : '·' }}</span>
          <strong>{{ row.label }}</strong>
        </div>
        <div class="risk-distribution-track" aria-hidden="true">
          <span :style="{ width: `${Math.min(100, Math.max(0, (row.value / maxValue) * 100))}%` }"></span>
        </div>
        <span class="risk-distribution-count" :aria-label="`${row.label}：${formatCount(row.value)}条`">{{ formatCount(row.value) }}<small>条</small></span>
      </div>
    </div>
    <div v-else class="visual-empty" role="status">
      <strong>当前条件暂无分层数据</strong>
      <span>请调整或清空当前筛选条件。</span>
    </div>

    <VisualizationTable v-if="rows.length" :section="section" :selectable="selectable" @select="item => emit('select', item)" />
  </div>
</template>
