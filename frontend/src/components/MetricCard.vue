<script setup>
defineProps({ metric: { type: Object, required: true }, highlighted: Boolean })
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
function display(metric) {
  if (metric.value == null) return '—'
  if (typeof metric.value !== 'number') return metric.value
  if (metric.unit === '%') return `${number.format(metric.value * 100)}%`
  return number.format(metric.value)
}
</script>
<template>
  <article class="metric-card" :class="{ highlighted }" :aria-label="`${metric.label}：${display(metric)}${metric.unit === '%' ? '' : metric.unit || ''}`">
    <p>{{ metric.label }}</p>
    <div class="metric-value-line">
      <strong>{{ display(metric) }}</strong>
      <small v-if="metric.unit !== '%' && metric.unit">{{ metric.unit }}</small>
    </div>
  </article>
</template>
