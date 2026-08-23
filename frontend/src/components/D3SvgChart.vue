<script setup>
import {
  arc, axisBottom, axisLeft, curveMonotoneX, extent, line, max, pie,
  scaleBand, scaleLinear, scaleOrdinal, select,
} from 'd3'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  section: { type: Object, required: true },
  presentation: { type: String, required: true },
  unit: { type: String, default: '' },
})
const emit = defineEmits(['select'])
const container = ref(null)
const svgElement = ref(null)
const tooltip = ref({ visible: false, x: 0, y: 0, text: '' })
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 })
let observer
let frame = 0
let chartTheme = {
  palette: ['#1E40AF', '#3B82F6', '#D97706', '#15803D', '#7C3AED'],
  axis: '#9DB0BD', grid: '#E3EAF0', text: '#536A78', strong: '#183F47',
  stroke: '#FFFFFF', negative: '#D97706', heatLow: '#EDF7F5', heatHigh: '#1B6268',
  heatDarkText: '#274652', heatLightText: '#FFFFFF',
}

function resolveChartTheme() {
  const styles = getComputedStyle(container.value)
  const value = (name, fallback) => styles.getPropertyValue(name).trim() || fallback
  return {
    palette: [1, 2, 3, 4, 5].map(index => value(`--chart-series-${index}`, chartTheme.palette[index - 1])),
    axis: value('--chart-axis', chartTheme.axis),
    grid: value('--chart-grid', chartTheme.grid),
    text: value('--chart-text', chartTheme.text),
    strong: value('--chart-text-strong', chartTheme.strong),
    stroke: value('--chart-mark-stroke', chartTheme.stroke),
    negative: value('--chart-negative', chartTheme.negative),
    heatLow: value('--chart-heat-low', chartTheme.heatLow),
    heatHigh: value('--chart-heat-high', chartTheme.heatHigh),
    heatDarkText: value('--chart-heat-dark-text', chartTheme.heatDarkText),
    heatLightText: value('--chart-heat-light-text', chartTheme.heatLightText),
  }
}

function format(value, unit = props.unit) {
  if (value == null) return '—'
  if (typeof value !== 'number') return String(value)
  if (unit === '%') return `${number.format(value * 100)}%`
  return number.format(value)
}

function short(value) { return typeof value === 'number' ? compact.format(value) : value }

function tooltipText(item) {
  if (props.presentation === 'scatter') return [
    item.name, `${props.section.visual?.x_label || 'X'}：${format(item.x, '天')}`,
    `${props.section.visual?.y_label || 'Y'}：${format(item.y)}`, `记录数：${format(item.size, '条')}`,
    item.cost == null ? '' : `平均成本：${format(item.cost, '美元')}`,
    item.high_cost_rate == null ? '' : `高费用率：${format(item.high_cost_rate, '%')}`, `分组：${item.group}`,
  ].filter(Boolean).join('\n')
  if (props.presentation === 'heatmap') return [
    `${item.x_label} × ${item.y_label}`, `记录数：${format(item.value, item.unit)}`,
    item.high_risk_rate == null ? '' : `Major/Extreme 比例：${format(item.high_risk_rate, '%')}`,
  ].filter(Boolean).join('\n')
  if (props.presentation === 'correlation') return [
    `${item.x_label} × ${item.y_label}`, `Pearson r：${Number(item.coefficient).toFixed(4)}`,
    `有效样本：${format(item.sample_size, '条')} 条`, '相关不等于因果',
  ].join('\n')
  return `${item.name || item.category}\n${format(item.value)}${props.unit && props.unit !== '%' ? ` ${props.unit}` : ''}`
}

function showTooltip(event, item) {
  if (!container.value) return
  const bounds = container.value.getBoundingClientRect()
  const target = event.currentTarget?.getBoundingClientRect?.()
  const pointerX = Number.isFinite(event.clientX) && event.clientX ? event.clientX - bounds.left : (target?.left || bounds.left) - bounds.left + (target?.width || 0) / 2
  const pointerY = Number.isFinite(event.clientY) && event.clientY ? event.clientY - bounds.top : (target?.top || bounds.top) - bounds.top
  tooltip.value = { visible: true, x: Math.max(8, Math.min(bounds.width - 190, pointerX + 10)), y: Math.max(8, pointerY - 12), text: tooltipText(item) }
}

function hideTooltip() { tooltip.value = { ...tooltip.value, visible: false } }

function makeInteractive(selection, itemAccessor = datum => datum) {
  selection.attr('tabindex', 0).attr('role', 'button').attr('aria-label', datum => tooltipText(itemAccessor(datum)).replaceAll('\n', '，'))
    .on('mouseenter focus', (event, datum) => showTooltip(event, itemAccessor(datum)))
    .on('mousemove', (event, datum) => showTooltip(event, itemAccessor(datum))).on('mouseleave blur', hideTooltip)
    .on('click', (_, datum) => emit('select', itemAccessor(datum)))
    .on('keydown', (event, datum) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); emit('select', itemAccessor(datum)) }
    })
}

function baseSvg(width, height) {
  const svg = select(svgElement.value)
  svg.selectAll('*').remove()
  svg.attr('viewBox', `0 0 ${width} ${height}`).attr('role', 'group').attr('aria-label', props.section.title)
  svg.append('title').text(props.section.title)
  svg.append('desc').text(props.section.visual?.summary?.text || `展示 ${props.section.items.length} 项聚合结果；可使用 Tab 键逐项读取和下钻。`)
  return svg
}

function styleAxis(group) {
  group.select('.domain').attr('stroke', chartTheme.axis)
  group.selectAll('.tick line').attr('stroke', chartTheme.grid)
  group.selectAll('.tick text').attr('fill', chartTheme.text).attr('font-size', 11)
}

function addValueLabel(group, x, y, text, anchor = 'start', fill = chartTheme.strong) {
  group.append('text').attr('x', x).attr('y', y).attr('text-anchor', anchor).attr('dominant-baseline', 'middle').attr('fill', fill).attr('font-size', 11).attr('font-weight', 600).text(text)
}

function drawBar(svg, width, height, items, correlation = false) {
  const margin = { top: 12, right: 64, bottom: 34, left: Math.min(width * .34, width < 430 ? 94 : 178) }
  const innerWidth = Math.max(60, width - margin.left - margin.right)
  const innerHeight = Math.max(80, height - margin.top - margin.bottom)
  const values = items.map(item => correlation ? Number(item.coefficient) : Number(item.value))
  const x = correlation ? scaleLinear().domain([-1, 1]).range([0, innerWidth]) : scaleLinear().domain([0, (max(values) || 1) * 1.18]).nice().range([0, innerWidth])
  const labels = items.map(item => correlation ? `${item.x_label} × ${item.y_label}` : item.name)
  const y = scaleBand().domain(labels).range([0, innerHeight]).padding(.28)
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  const bottom = root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).ticks(width < 450 ? 4 : 6).tickFormat(short).tickSize(-innerHeight)); styleAxis(bottom)
  styleAxis(root.append('g').call(axisLeft(y).tickSize(0)))
  if (correlation) root.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', innerHeight).attr('stroke', chartTheme.axis).attr('stroke-width', 1.5)
  const bars = root.selectAll('.d3-bar').data(items).join('rect').attr('class', 'd3-mark d3-bar')
    .attr('x', item => correlation ? Math.min(x(0), x(item.coefficient)) : 0)
    .attr('y', item => y(correlation ? `${item.x_label} × ${item.y_label}` : item.name))
    .attr('width', item => correlation ? Math.abs(x(item.coefficient) - x(0)) : x(item.value)).attr('height', y.bandwidth()).attr('rx', 4)
    .attr('fill', item => correlation && item.coefficient < 0 ? chartTheme.negative : chartTheme.palette[0])
  makeInteractive(bars)
  items.forEach(item => {
    const value = correlation ? Number(item.coefficient) : Number(item.value)
    const labelX = correlation ? x(value) + (value >= 0 ? 7 : -7) : Math.min(innerWidth - 2, x(value) + 6)
    addValueLabel(root, labelX, (y(correlation ? `${item.x_label} × ${item.y_label}` : item.name) || 0) + y.bandwidth() / 2, correlation ? value.toFixed(4) : format(value), value < 0 ? 'end' : 'start')
  })
}

function drawPie(svg, width, height, items) {
  const legendHeight = Math.min(68, Math.ceil(items.length / (width < 500 ? 2 : 4)) * 20)
  const radius = Math.max(42, Math.min(width * .22, (height - legendHeight) * .38))
  const centerX = width / 2
  const centerY = (height - legendHeight) / 2 + 4
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0) || 1
  const pieData = pie().sort(null).value(item => item.value)(items)
  const path = arc().innerRadius(radius * .54).outerRadius(radius)
  const labelArc = arc().innerRadius(radius * .77).outerRadius(radius * .77)
  const root = svg.append('g').attr('transform', `translate(${centerX},${centerY})`)
  const slices = root.selectAll('.d3-slice').data(pieData).join('path').attr('class', 'd3-mark d3-slice').attr('d', path)
    .attr('fill', (_, index) => chartTheme.palette[index % chartTheme.palette.length]).attr('stroke', chartTheme.stroke).attr('stroke-width', 2)
  makeInteractive(slices, datum => datum.data)
  root.selectAll('.d3-pie-label').data(pieData.filter(item => item.data.value / total >= .055)).join('text')
    .attr('transform', item => `translate(${labelArc.centroid(item)})`).attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
    .attr('fill', chartTheme.heatLightText).attr('font-size', 10).attr('font-weight', 700).text(item => `${number.format(item.data.value / total * 100)}%`)
  const columns = width < 500 ? 2 : Math.min(4, items.length)
  const cellWidth = width / columns
  const legend = svg.append('g').attr('transform', `translate(0,${height - legendHeight + 5})`)
  items.forEach((item, index) => {
    const x = index % columns * cellWidth + 8; const y = Math.floor(index / columns) * 20
    legend.append('rect').attr('x', x).attr('y', y + 2).attr('width', 11).attr('height', 11).attr('rx', 2).attr('fill', chartTheme.palette[index % chartTheme.palette.length])
    legend.append('text').attr('x', x + 16).attr('y', y + 8).attr('dominant-baseline', 'middle').attr('fill', chartTheme.text).attr('font-size', 10).text(`${String(item.name).slice(0, 18)} ${number.format(item.value / total * 100)}%`)
  })
  root.append('text').attr('text-anchor', 'middle').attr('y', -3).attr('fill', chartTheme.text).attr('font-size', 11).text('结构合计')
  root.append('text').attr('text-anchor', 'middle').attr('y', 15).attr('fill', chartTheme.strong).attr('font-size', 14).attr('font-weight', 800).text(short(total))
}

function drawStacked(svg, width, height, items) {
  const margin = { top: 32, right: 20, bottom: 34, left: 18 }
  const innerWidth = width - margin.left - margin.right
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0) || 1
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  let cursor = 0
  const barY = Math.max(34, (height - margin.top - margin.bottom) / 2 - 25)
  items.forEach((item, index) => {
    const itemWidth = innerWidth * item.value / total
    const rect = root.append('rect').datum(item).attr('class', 'd3-mark').attr('x', cursor).attr('y', barY).attr('width', itemWidth).attr('height', 44).attr('fill', chartTheme.palette[index % chartTheme.palette.length])
    makeInteractive(rect)
    if (itemWidth > 58) addValueLabel(root, cursor + itemWidth / 2, barY + 22, `${number.format(item.value / total * 100)}%`, 'middle', chartTheme.heatLightText)
    const lx = index % 3 * innerWidth / 3; const ly = Math.floor(index / 3) * 19
    root.append('rect').attr('x', lx).attr('y', ly).attr('width', 10).attr('height', 10).attr('fill', chartTheme.palette[index % chartTheme.palette.length])
    root.append('text').attr('x', lx + 15).attr('y', ly + 8).attr('fill', chartTheme.text).attr('font-size', 10).text(item.name)
    cursor += itemWidth
  })
  styleAxis(root.append('g').attr('transform', `translate(0,${barY + 44})`).call(axisBottom(scaleLinear().domain([0, total]).range([0, innerWidth])).ticks(5).tickFormat(short)))
}

function drawLine(svg, width, height, items) {
  const ordered = [...items].sort((a, b) => Number(String(a.name).match(/\d+/)?.[0] || 0) - Number(String(b.name).match(/\d+/)?.[0] || 0))
  const margin = { top: 24, right: 42, bottom: 42, left: 54 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x = scaleBand().domain(ordered.map(item => item.name)).range([0, innerWidth]).padding(.5)
  const y = scaleLinear().domain([0, (max(ordered, item => item.value) || 1) * 1.16]).nice().range([innerHeight, 0])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  root.append('path').datum(ordered).attr('fill', 'none').attr('stroke', chartTheme.palette[0]).attr('stroke-width', 3).attr('d', line().x(item => (x(item.name) || 0) + x.bandwidth() / 2).y(item => y(item.value)).curve(curveMonotoneX))
  const points = root.selectAll('.d3-point').data(ordered).join('circle').attr('class', 'd3-mark d3-point').attr('cx', item => (x(item.name) || 0) + x.bandwidth() / 2).attr('cy', item => y(item.value)).attr('r', 6).attr('fill', chartTheme.palette[0]).attr('stroke', chartTheme.stroke).attr('stroke-width', 2)
  makeInteractive(points)
  ordered.forEach(item => addValueLabel(root, (x(item.name) || 0) + x.bandwidth() / 2, y(item.value) - 12, short(item.value), 'middle'))
}

function drawGrouped(svg, width, height, items) {
  const series = [...new Map(items.flatMap(item => item.series).map(value => [value.key, value])).values()]
  const margin = { top: 32, right: 22, bottom: 48, left: 52 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x0 = scaleBand().domain(items.map(item => item.category)).range([0, innerWidth]).padding(.24)
  const x1 = scaleBand().domain(series.map(item => item.key)).range([0, x0.bandwidth()]).padding(.08)
  const maxValue = max(items.flatMap(item => item.series), item => item.value) || 1
  const y = scaleLinear().domain([0, maxValue * 1.12]).nice().range([innerHeight, 0])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x0)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  const flat = items.flatMap(item => item.series.map(value => ({ ...value, category: item.category })))
  const bars = root.selectAll('.d3-grouped').data(flat).join('rect').attr('class', 'd3-mark')
    .attr('x', item => (x0(item.category) || 0) + (x1(item.key) || 0)).attr('y', item => y(item.value)).attr('width', x1.bandwidth())
    .attr('height', item => innerHeight - y(item.value)).attr('rx', 3).attr('fill', item => chartTheme.palette[series.findIndex(value => value.key === item.key) % chartTheme.palette.length])
  makeInteractive(bars, item => ({ name: `${item.category} · ${item.label}`, value: item.value, category: item.category }))
  series.forEach((item, index) => {
    root.append('rect').attr('x', index * 130).attr('y', -25).attr('width', 10).attr('height', 10).attr('fill', chartTheme.palette[index % chartTheme.palette.length])
    root.append('text').attr('x', index * 130 + 15).attr('y', -17).attr('fill', chartTheme.text).attr('font-size', 10).text(item.label)
  })
}

function drawScatter(svg, width, height, items) {
  const margin = { top: 34, right: 28, bottom: 44, left: 58 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const xExtent = extent(items, item => item.x); const yExtent = extent(items, item => item.y)
  const x = scaleLinear().domain([Math.min(0, xExtent[0] || 0), (xExtent[1] || 1) * 1.08]).nice().range([0, innerWidth])
  const y = scaleLinear().domain([Math.min(0, yExtent[0] || 0), (yExtent[1] || 1) * 1.12]).nice().range([innerHeight, 0])
  const size = scaleLinear().domain([0, max(items, item => item.size) || 1]).range([5, 18])
  const groups = [...new Set(items.map(item => String(item.group)))]; const color = scaleOrdinal(groups, chartTheme.palette)
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).ticks(6).tickFormat(short).tickSize(-innerHeight)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  const points = root.selectAll('.d3-bubble').data(items).join('circle').attr('class', 'd3-mark d3-bubble').attr('cx', item => x(item.x)).attr('cy', item => y(item.y)).attr('r', item => size(item.size)).attr('fill', item => color(String(item.group))).attr('fill-opacity', .84).attr('stroke', chartTheme.stroke).attr('stroke-width', 1.5)
  makeInteractive(points)
  groups.slice(0, 5).forEach((group, index) => {
    root.append('circle').attr('cx', index * 92).attr('cy', -19).attr('r', 5).attr('fill', color(group))
    root.append('text').attr('x', index * 92 + 9).attr('y', -16).attr('fill', chartTheme.text).attr('font-size', 10).text(group)
  })
}

function drawHeatmap(svg, width, height, items) {
  const xLabels = [...new Set(items.map(item => item.x_label))]; const yLabels = [...new Set(items.map(item => item.y_label))]
  const margin = { top: 10, right: 22, bottom: 64, left: width < 430 ? 66 : 86 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x = scaleBand().domain(xLabels).range([0, innerWidth]).padding(.04); const y = scaleBand().domain(yLabels).range([0, innerHeight]).padding(.04)
  const maxValue = max(items, item => item.value) || 1; const color = scaleLinear().domain([0, maxValue]).range([chartTheme.heatLow, chartTheme.heatHigh])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  const bottom = root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).tickSize(0)); styleAxis(bottom)
  bottom.selectAll('text').attr('transform', 'rotate(-22)').attr('text-anchor', 'end')
  styleAxis(root.append('g').call(axisLeft(y).tickSize(0)))
  const cells = root.selectAll('.d3-cell').data(items).join('rect').attr('class', 'd3-mark d3-cell').attr('x', item => x(item.x_label)).attr('y', item => y(item.y_label)).attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 2).attr('fill', item => color(item.value))
  makeInteractive(cells)
  root.selectAll('.d3-cell-label').data(items).join('text').attr('x', item => (x(item.x_label) || 0) + x.bandwidth() / 2).attr('y', item => (y(item.y_label) || 0) + y.bandwidth() / 2).attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('font-size', width < 430 ? 8 : 10).attr('fill', item => item.value > maxValue * .55 ? chartTheme.heatLightText : chartTheme.heatDarkText).text(item => short(item.value))
  const gradientId = `heat-${Math.random().toString(36).slice(2)}`; const gradient = svg.append('defs').append('linearGradient').attr('id', gradientId)
  gradient.append('stop').attr('offset', '0%').attr('stop-color', chartTheme.heatLow); gradient.append('stop').attr('offset', '100%').attr('stop-color', chartTheme.heatHigh)
  svg.append('rect').attr('x', margin.left + innerWidth / 2 - 60).attr('y', height - 20).attr('width', 120).attr('height', 9).attr('rx', 4).attr('fill', `url(#${gradientId})`)
  svg.append('text').attr('x', margin.left + innerWidth / 2 - 70).attr('y', height - 12).attr('text-anchor', 'end').attr('font-size', 10).attr('fill', chartTheme.text).text('低')
  svg.append('text').attr('x', margin.left + innerWidth / 2 + 70).attr('y', height - 12).attr('font-size', 10).attr('fill', chartTheme.text).text('高')
}

function render() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!container.value || !svgElement.value || !props.section.items?.length) return
    chartTheme = resolveChartTheme()
    const width = Math.max(280, container.value.clientWidth); const height = Math.max(220, container.value.clientHeight)
    const svg = baseSvg(width, height); const items = props.section.items
    if (props.presentation === 'pie') drawPie(svg, width, height, items)
    else if (props.presentation === 'stacked_bar') drawStacked(svg, width, height, items)
    else if (props.presentation === 'quantile') drawLine(svg, width, height, items)
    else if (props.presentation === 'grouped_bar') drawGrouped(svg, width, height, items)
    else if (props.presentation === 'scatter') drawScatter(svg, width, height, items)
    else if (props.presentation === 'heatmap') drawHeatmap(svg, width, height, items)
    else drawBar(svg, width, height, items, props.presentation === 'correlation')
  })
}

watch(() => [props.section, props.presentation], async () => { await nextTick(); render() }, { deep: true })
onMounted(() => { render(); observer = new ResizeObserver(render); observer.observe(container.value) })
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame) })
</script>

<template>
  <div ref="container" class="chart-canvas d3-chart-canvas">
    <svg ref="svgElement" class="d3-chart-svg"></svg>
    <div v-show="tooltip.visible" class="d3-tooltip" :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }" role="tooltip">{{ tooltip.text }}</div>
  </div>
</template>
