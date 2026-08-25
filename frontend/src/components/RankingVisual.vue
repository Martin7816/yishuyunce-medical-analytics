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

const numberFormat = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
  useGrouping: false,
})

const items = computed(() => Array.isArray(props.section.items) ? props.section.items : [])
const rankingKicker = computed(() => props.section.key === 'hospitals' ? '医院排行' : '操作排行')
const unit = computed(() => {
  if (props.section.visual?.unit || props.section.unit) return props.section.visual?.unit || props.section.unit
  const context = `${props.section.key || ''} ${props.section.title || ''}`
  if (/(收费|成本|金额|费用)/.test(context)) return '美元'
  if (/(住院时长|天数)/.test(context)) return '天'
  if (/(比例|率)/.test(context)) return '%'
  return '条'
})

// The maximum is used only to place the dots on a visual guide; source items
// are kept in the order returned by the API and no frontend ranking is done.
const visualMax = computed(() => {
  const values = items.value
    .map(item => typeof item.value === 'number' ? Math.max(item.value, 0) : 0)
  return Math.max(...values, 1)
})

function itemLabel(item) {
  return displaySectionItemValue(item.name ?? item.category ?? '未分类', props.section)
}

function formatValue(value) {
  if (value == null) return '—'
  return typeof value === 'number' ? numberFormat.format(value) : displayText(value)
}

function rankLabel(index) {
  return String(index + 1).padStart(2, '0')
}

function dotPosition(item) {
  if (typeof item.value !== 'number' || item.value <= 0) return '0%'
  return `${Math.min((item.value / visualMax.value) * 100, 100)}%`
}
</script>

<template>
  <div class="ranking-visual">
    <div class="ranking-visual-heading">
      <div>
        <span class="ranking-visual-kicker">{{ rankingKicker }}</span>
        <strong>TOP {{ items.length }}</strong>
      </div>
      <span>单位：{{ unit }}</span>
    </div>

    <div v-if="items.length" class="ranking-visual-list" role="list" :aria-label="displayText(section.title)">
      <div
        v-for="(item, index) in items"
        :key="`${section.key}-ranking-${item.name ?? item.category ?? index}`"
        class="ranking-lollipop-row"
        role="listitem"
        :aria-label="`${itemLabel(item)}：${formatValue(item.value)}${unit}`"
      >
        <span class="ranking-rank-badge" aria-hidden="true">{{ rankLabel(index) }}</span>
        <div class="ranking-lollipop-main">
          <div class="ranking-lollipop-meta">
            <strong>{{ itemLabel(item) }}</strong>
            <span class="ranking-lollipop-value">{{ formatValue(item.value) }} {{ unit }}</span>
          </div>
          <div class="ranking-lollipop-track" aria-hidden="true">
            <span class="ranking-lollipop-tick" :style="{ left: dotPosition(item) }"></span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="visual-empty" role="status">
      <strong>当前条件暂无排行数据</strong>
      <span>请调整或清空当前筛选条件。</span>
    </div>

    <VisualizationTable
      v-if="items.length"
      :section="section"
      :selectable="selectable"
      @select="item => emit('select', item)"
    />
  </div>
</template>
