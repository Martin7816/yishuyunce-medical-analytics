<script setup>
import { computed } from 'vue'
import {
  displaySectionItemValue,
  displayText,
} from '../domain/displayLabels.js'
import VisualizationTable from './VisualizationTable.vue'

const props = defineProps({
  section: { type: Object, required: true },
  selectable: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])

const levelOrder = Object.freeze(['Minor', 'Moderate', 'Major', 'Extreme'])
const numberFormat = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
  useGrouping: false,
})

const unit = computed(() => props.section.visual?.unit || props.section.unit || '条')

// Preserve the semantic APR order without ranking or aggregating values in the UI.
const rows = computed(() => {
  const items = Array.isArray(props.section.items) ? props.section.items : []
  const byName = new Map(items.map(item => [item.name, item]))
  const ordered = levelOrder.map(name => byName.get(name)).filter(Boolean)
  const remaining = items.filter(item => !levelOrder.includes(item.name))
  return [...ordered, ...remaining].map((item, index) => {
    const levelIndex = levelOrder.indexOf(item.name)
    return {
      ...item,
      key: `${item.name || 'level'}-${index}`,
      label: displaySectionItemValue(item.name || '未分类', props.section),
      value: typeof item.value === 'number' && Number.isFinite(item.value) ? item.value : null,
      levelIndex,
      displayIndex: levelIndex >= 0 ? levelIndex + 1 : index + 1,
      tone: levelIndex >= 0 ? levelOrder[levelIndex].toLowerCase() : 'other',
    }
  })
})

function formatValue(value) {
  if (value == null) return '—'
  return typeof value === 'number' ? numberFormat.format(value) : displayText(value)
}
</script>

<template>
  <div class="severity-ladder-visual">
    <div class="severity-ladder-header">
      <div>
        <span class="severity-ladder-kicker">严重程度分层</span>
        <strong>{{ rows.length }}</strong>
        <small>个等级</small>
      </div>
      <span class="severity-ladder-direction" aria-label="严重程度由轻到重">
        <span>轻</span>
        <span aria-hidden="true">→</span>
        <span>重</span>
      </span>
    </div>

    <div v-if="rows.length" class="severity-ladder" role="list" :aria-label="`${displayText(section.title)}等级明细`">
      <div
        v-for="row in rows"
        :key="row.key"
        class="severity-level"
        :class="`severity-level--${row.tone}`"
        role="listitem"
        :aria-label="`${row.label}：${formatValue(row.value)}${unit}`"
      >
        <div class="severity-level-head">
          <span class="severity-level-index" aria-hidden="true">{{ String(row.displayIndex).padStart(2, '0') }}</span>
          <span>等级 {{ row.displayIndex }}</span>
        </div>
        <strong class="severity-level-label">{{ row.label }}</strong>
        <div class="severity-level-count">
          <strong>{{ formatValue(row.value) }}</strong>
          <small>{{ unit }}</small>
        </div>
      </div>
    </div>

    <div v-else class="visual-empty" role="status">
      <strong>当前条件暂无严重程度数据</strong>
      <span>请调整或清空当前筛选条件。</span>
    </div>

    <p v-if="rows.length" class="severity-ladder-note">
      <span aria-hidden="true">●</span>
      <span>按严重程度等级展示接口返回的住院出院记录数；颜色用于辅助区分等级，数字为事实值。</span>
    </p>

    <VisualizationTable
      v-if="rows.length"
      :section="section"
      :selectable="selectable"
      @select="item => emit('select', item)"
    />
  </div>
</template>
