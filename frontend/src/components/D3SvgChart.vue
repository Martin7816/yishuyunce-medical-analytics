<script setup>
import {
  arc, axisBottom, axisLeft, curveMonotoneX, extent, line, max, pie,
  scaleBand, scaleLinear, scaleOrdinal, select,
} from 'd3'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  displayFieldLabel,
  displaySectionItemValue,
  displayText,
  displayValue,
} from '../domain/displayLabels.js'
import {
  scatterLegendLayout,
  scatterPointOffset,
  scatterPointRadius,
} from '../domain/scatterPresentation.js'

const props = defineProps({
  section: { type: Object, required: true },
  presentation: { type: String, required: true },
  unit: { type: String, default: '' },
  selectable: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])
const container = ref(null)
const svgElement = ref(null)
const tooltip = ref({ visible: false, x: 0, y: 0, text: '' })
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })
const compact = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 })
let observer
let frame = 0
let chartTheme = {
  palette: ['#1E40AF', '#3B82F6', '#D97706', '#15803D', '#7C3AED'],
  axis: '#9DB0BD', grid: '#E3EAF0', text: '#536A78', strong: '#183F47',
  stroke: '#FFFFFF', negative: '#D97706', heatLow: '#EDF7F5', heatHigh: '#1B6268',
  heatDarkText: '#274652', heatLightText: '#FFFFFF',
}

const VISUAL_LABELS = Object.freeze({
  '0 to 17': '0–17岁',
  '18 to 29': '18–29岁',
  '30 to 49': '30–49岁',
  '50 to 69': '50–69岁',
  '70 or Older': '70岁及以上',
  'Private Health Insurance': '商业医疗保险',
  'Managed Care, Unsp': '管理式医疗（未说明）',
  'Blue Cross/Blue Shield': '蓝十字/蓝盾',
  'Self-Pay': '自费',
  'Miscellaneous/Other': '其他/杂项',
  'Federal/State/Local': '联邦/州/地方',
  'Department of Corr.': '惩教部门',
  Minor: '轻症',
  Moderate: '中症',
  Major: '重症',
  Extreme: '极重症',
  SEPTICEMIA: '败血症',
  'CORONAVIRUS DISEASE 2019 (COVID-19)': '2019冠状病毒病（COVID-19）',
  'HEART FAILURE': '心力衰竭',
  'COMPLICATIONS SPECIFIED DURING CHILDBIRTH': '分娩相关并发症',
  'DIABETES MELLITUS WITH COMPLICATION': '糖尿病并发症',
  'ALCOHOL-RELATED DISORDERS': '酒精相关疾病',
  'SPECTRUM AND OTHER PSYCHOTIC DISORDERS': '精神障碍谱系',
  OSTEOARTHRITIS: '骨关节炎',
  'CARDIAC DYSRHYTHMIAS': '心律失常',
})

function truncateLabel(value, maxLength) {
  const text = String(value ?? '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text
}

function wrapAxisLabel(value, maxChars, maxLines = 2) {
  const characters = Array.from(String(value ?? ''))
  if (!characters.length) return ['']
  const lines = []
  for (let index = 0; index < characters.length && lines.length < maxLines; index += maxChars) {
    lines.push(characters.slice(index, index + maxChars).join(''))
  }
  if (characters.length > maxChars * maxLines) {
    const last = Array.from(lines[maxLines - 1] || '')
    lines[maxLines - 1] = `${last.slice(0, Math.max(1, maxChars - 1)).join('')}…`
  }
  return lines
}

function visualLabelText(value, key = props.section.key, field = 'name') {
  const raw = String(value ?? '')
  const section = key === props.section.key ? props.section : { ...props.section, key }
  const translated = displaySectionItemValue(raw, section, field)
  return translated || VISUAL_LABELS[raw] || raw
}

function visualLabel(value, key = props.section.key, field = 'name', maxLengthOverride = null) {
  const maxLength = maxLengthOverride || (key === 'hospital_top10' || key === 'ranking' ? 18 : key === 'disease_top10' ? 27 : key === 'correlation' ? 24 : 19)
  return truncateLabel(visualLabelText(value, key, field), maxLength)
}

function axisLabel(item, correlation = false, maxLengthOverride = null) {
  if (correlation) return truncateLabel(`${displayText(displayFieldLabel(item.x_label))} × ${displayText(displayFieldLabel(item.y_label))}`, 24)
  const field = item.name != null ? 'name' : item.category != null ? 'category' : item.x_label != null ? 'x_label' : 'y_label'
  const raw = item[field] || '该分组'
  return visualLabel(raw, props.section.key, field, maxLengthOverride)
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

function ageGroupShare(item) {
  if (props.section.key !== 'age_severity_matrix' || item?.x_label == null) return null
  const total = props.section.items
    .filter(candidate => candidate.x_label === item.x_label)
    .reduce((sum, candidate) => sum + (typeof candidate.value === 'number' ? candidate.value : 0), 0)
  return total > 0 && typeof item.value === 'number' ? item.value / total : 0
}

function tooltipText(item) {
  if (props.presentation === 'scatter') {
    const isOverviewRelation = props.section.key === 'cost_los_overview'
    const chargeCostGap = typeof item.y === 'number' && typeof item.cost === 'number' ? item.y - item.cost : null
    return [
      visualLabelText(item.name), `${displayText(props.section.visual?.x_label || '平均住院时长')}：${format(item.x, '天')}`,
      `${displayText(props.section.visual?.y_label || '平均收费')}：${format(item.y, '美元')}`, `记录数：${format(item.size, '条')}`,
      item.cost == null ? '' : `平均成本：${format(item.cost, '美元')}`,
      isOverviewRelation && chargeCostGap != null ? `收费成本差：${format(chargeCostGap, '美元')}` : '',
      item.high_cost_rate == null ? '' : `高费用率：${format(item.high_cost_rate, '%')}`,
      isOverviewRelation ? '' : `分组：${visualLabelText(item.group, 'severity')}`,
    ].filter(Boolean).join('\n')
  }
  if (props.presentation === 'heatmap') return [
    `${visualLabel(item.x_label, 'age')} × ${visualLabel(item.y_label, 'severity')}`, `病例量：${format(item.value, item.unit)}`,
    ageGroupShare(item) == null ? '' : `年龄组内占比：${format(ageGroupShare(item), '%')}`,
  ].filter(Boolean).join('\n')
  if (props.presentation === 'correlation') return [
    `${displayText(displayFieldLabel(item.x_label))} × ${displayText(displayFieldLabel(item.y_label))}`, `皮尔逊相关系数：${Number(item.coefficient).toFixed(4)}`,
    `有效样本：${format(item.sample_size, '条')} 条`, '相关不等于因果',
  ].join('\n')
  return `${visualLabelText(item.name || item.category)}\n${format(item.value)}${props.unit && props.unit !== '%' ? ` ${props.unit}` : ''}`
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
  selection
    .on('mouseenter', (event, datum) => showTooltip(event, itemAccessor(datum)))
    .on('mousemove', (event, datum) => showTooltip(event, itemAccessor(datum)))
    .on('mouseleave', hideTooltip)
  if (!props.selectable) return
  selection
    .attr('tabindex', 0)
    .attr('role', 'button')
    .attr('aria-label', datum => tooltipText(itemAccessor(datum)).replaceAll('\n', '，'))
    .on('focus', (event, datum) => showTooltip(event, itemAccessor(datum)))
    .on('blur', hideTooltip)
    .on('click', (_, datum) => emit('select', itemAccessor(datum)))
    .on('keydown', (event, datum) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); emit('select', itemAccessor(datum)) }
    })
}

function baseSvg(width, height) {
  const svg = select(svgElement.value)
  svg.selectAll('*').remove()
  svg.attr('viewBox', `0 0 ${width} ${height}`).attr('role', 'group').attr('aria-label', displayText(props.section.title))
  svg.append('title').text(displayText(props.section.title))
  svg.append('desc').text(displayText(props.section.visual?.summary?.text || (props.selectable
    ? `展示 ${props.section.items.length} 项聚合结果；可使用 Tab 键逐项读取和下钻。`
    : `展示 ${props.section.items.length} 项聚合结果；下方数据表提供精确数值。`)))
  return svg
}

function styleAxis(group, fontSize = 11) {
  group.select('.domain').attr('stroke', chartTheme.axis)
  group.selectAll('.tick line').attr('stroke', chartTheme.grid)
  group.selectAll('.tick text').attr('fill', chartTheme.text).attr('font-size', fontSize)
}

function addValueLabel(group, x, y, text, anchor = 'start', fill = chartTheme.strong) {
  group.append('text').attr('x', x).attr('y', y).attr('text-anchor', anchor).attr('dominant-baseline', 'middle').attr('fill', fill).attr('font-size', 11).attr('font-weight', 600).text(text)
}

function drawCorrelation(svg, width, height, items) {
  const margin = { top: 18, right: 28, bottom: 72, left: 52 }
  const innerWidth = Math.max(160, width - margin.left - margin.right)
  const innerHeight = Math.max(120, height - margin.top - margin.bottom)
  const labels = items.map(item => axisLabel(item, true))
  const x = scaleBand().domain(items.map((_, index) => index)).range([0, innerWidth]).padding(width < 430 ? .24 : .34)
  const y = scaleLinear().domain([0, 1]).range([innerHeight, 0])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  const bottom = root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).tickSize(0).tickFormat(index => labels[Number(index)] || ''))
  styleAxis(bottom, 12)
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(value => Number(value).toFixed(1)).tickSize(-innerWidth)), 11)
  const bars = root.selectAll('.d3-correlation-bar').data(items).join('rect').attr('class', 'd3-mark d3-correlation-bar')
    .attr('x', (_, index) => x(index))
    .attr('y', item => y(Math.max(0, Math.min(1, Number(item.coefficient) || 0))))
    .attr('width', x.bandwidth())
    .attr('height', item => innerHeight - y(Math.max(0, Math.min(1, Number(item.coefficient) || 0))))
    .attr('rx', 4)
    .attr('fill', chartTheme.palette[0])
  makeInteractive(bars)
  items.forEach((item, index) => {
    const value = Math.max(0, Math.min(1, Number(item.coefficient) || 0))
    addValueLabel(root, (x(index) || 0) + x.bandwidth() / 2, Math.max(10, y(value) - 10), value.toFixed(4), 'middle')
  })
}

function drawBar(svg, width, height, items) {
  const isHospitalRanking = props.section.key === 'hospital_top10' || props.section.key === 'ranking'
  const isDiseaseChart = ['disease_top10', 'diseases', 'top10'].includes(props.section.key)
  const wrapDiseaseLabels = isDiseaseChart && items.length <= 6
  const labelLength = isHospitalRanking
    ? (width < 430 ? 10 : width < 600 ? 13 : 18)
    : isDiseaseChart
      ? (width < 430 ? 10 : width < 600 ? 14 : 19)
      : null
  const labelMargin = isHospitalRanking
    ? (width < 430 ? 126 : width < 600 ? 164 : 224)
    : isDiseaseChart
      ? (width < 430 ? 132 : width < 600 ? 184 : 238)
      : Math.min(width * .34, width < 430 ? 94 : 178)
  const margin = { top: 12, right: 64, bottom: 34, left: labelMargin }
  const innerWidth = Math.max(60, width - margin.left - margin.right)
  const innerHeight = Math.max(80, height - margin.top - margin.bottom)
  const values = items.map(item => Number(item.value))
  const x = scaleLinear().domain([0, (max(values) || 1) * 1.18]).nice().range([0, innerWidth])
  const labels = items.map(item => {
    if (!wrapDiseaseLabels) return [axisLabel(item, false, labelLength)]
    const field = item.name != null ? 'name' : item.category != null ? 'category' : item.x_label != null ? 'x_label' : 'y_label'
    return wrapAxisLabel(visualLabelText(item[field] || '该分组', props.section.key, field), labelLength)
  })
  const y = scaleBand().domain(items.map((_, index) => index)).range([0, innerHeight]).padding(.28)
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  const bottom = root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).ticks(width < 450 ? 4 : 6).tickFormat(short).tickSize(-innerHeight)); styleAxis(bottom, 10)
  const yAxis = root.append('g').call(axisLeft(y).tickSize(0).tickFormat(index => labels[Number(index)]?.[0] || ''))
  styleAxis(yAxis, 12)
  if (wrapDiseaseLabels) {
    yAxis.selectAll('.tick text').each(function (_, index) {
      const tick = select(this)
      const lines = labels[index] || ['']
      tick.text(null)
      lines.forEach((line, lineIndex) => {
        tick.append('tspan')
          .attr('x', -9)
          .attr('dy', lineIndex === 0 ? `${0.32 - (lines.length - 1) * 0.5}em` : '1em')
          .text(line)
      })
    })
  }
  yAxis.selectAll('.tick').each(function (_, index) {
    select(this).append('title').text(visualLabelText(items[Number(index)]?.name || items[Number(index)]?.category || '该分组', props.section.key))
  })
  const bars = root.selectAll('.d3-bar').data(items).join('rect').attr('class', 'd3-mark d3-bar')
    .attr('x', 0)
    .attr('y', (_, index) => y(index))
    .attr('width', item => x(item.value)).attr('height', y.bandwidth()).attr('rx', 4)
    .attr('fill', chartTheme.palette[0])
  makeInteractive(bars)
  items.forEach((item, index) => {
    const value = Number(item.value)
    const labelX = Math.min(innerWidth - 2, x(value) + 6)
    addValueLabel(root, labelX, (y(index) || 0) + y.bandwidth() / 2, format(value), 'start')
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
    legend.append('text').attr('x', x + 16).attr('y', y + 8).attr('dominant-baseline', 'middle').attr('fill', chartTheme.text).attr('font-size', 10).text(`${visualLabel(item.name, props.section.key)} ${number.format(item.value / total * 100)}%`)
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
    root.append('text').attr('x', lx + 15).attr('y', ly + 8).attr('fill', chartTheme.text).attr('font-size', 10).text(visualLabel(item.name, props.section.key))
    cursor += itemWidth
  })
  styleAxis(root.append('g').attr('transform', `translate(0,${barY + 44})`).call(axisBottom(scaleLinear().domain([0, total]).range([0, innerWidth])).ticks(5).tickFormat(short)))
}

function drawLine(svg, width, height, items) {
  const ordered = [...items].sort((a, b) => Number(String(a.name).match(/\d+/)?.[0] || 0) - Number(String(b.name).match(/\d+/)?.[0] || 0))
  const margin = { top: 24, right: 42, bottom: 42, left: 54 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x = scaleBand().domain(ordered.map(item => visualLabel(item.name, 'quantiles'))).range([0, innerWidth]).padding(.5)
  const y = scaleLinear().domain([0, (max(ordered, item => item.value) || 1) * 1.16]).nice().range([innerHeight, 0])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  root.append('path').datum(ordered).attr('fill', 'none').attr('stroke', chartTheme.palette[0]).attr('stroke-width', 3).attr('d', line().x(item => (x(visualLabel(item.name, 'quantiles')) || 0) + x.bandwidth() / 2).y(item => y(item.value)).curve(curveMonotoneX))
  const points = root.selectAll('.d3-point').data(ordered).join('circle').attr('class', 'd3-mark d3-point').attr('cx', item => (x(visualLabel(item.name, 'quantiles')) || 0) + x.bandwidth() / 2).attr('cy', item => y(item.value)).attr('r', 6).attr('fill', chartTheme.palette[0]).attr('stroke', chartTheme.stroke).attr('stroke-width', 2)
  makeInteractive(points)
  ordered.forEach(item => addValueLabel(root, (x(visualLabel(item.name, 'quantiles')) || 0) + x.bandwidth() / 2, y(item.value) - 12, short(item.value), 'middle'))
}

function drawGrouped(svg, width, height, items) {
  const series = [...new Map(items.flatMap(item => item.series).map(value => [value.key, value])).values()]
  const margin = { top: 32, right: 22, bottom: 48, left: 52 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x0 = scaleBand().domain(items.map(item => visualLabel(item.category, props.section.key))).range([0, innerWidth]).padding(.24)
  const x1 = scaleBand().domain(series.map(item => item.key)).range([0, x0.bandwidth()]).padding(.08)
  const maxValue = max(items.flatMap(item => item.series), item => item.value) || 1
  const y = scaleLinear().domain([0, maxValue * 1.12]).nice().range([innerHeight, 0])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x0)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  const flat = items.flatMap(item => item.series.map(value => ({ ...value, category: item.category })))
  const bars = root.selectAll('.d3-grouped').data(flat).join('rect').attr('class', 'd3-mark')
    .attr('x', item => (x0(visualLabel(item.category, props.section.key)) || 0) + (x1(item.key) || 0)).attr('y', item => y(item.value)).attr('width', x1.bandwidth())
    .attr('height', item => innerHeight - y(item.value)).attr('rx', 3).attr('fill', item => chartTheme.palette[series.findIndex(value => value.key === item.key) % chartTheme.palette.length])
  makeInteractive(bars, item => ({ name: `${item.category} · ${item.label}`, value: item.value, category: item.category }))
  series.forEach((item, index) => {
    root.append('rect').attr('x', index * 130).attr('y', -25).attr('width', 10).attr('height', 10).attr('fill', chartTheme.palette[index % chartTheme.palette.length])
    root.append('text').attr('x', index * 130 + 15).attr('y', -17).attr('fill', chartTheme.text).attr('font-size', 10).text(displayText(item.label))
  })
}

function drawScatter(svg, width, height, items) {
  const isOverviewRelation = props.section.key === 'cost_los_overview'
  const groups = [...new Set(items.map(item => String(item.group)))]
  const legendGroups = groups.slice(0, 5)
  const provisionalInnerWidth = width - 58 - 28
  const legendLayout = scatterLegendLayout(provisionalInnerWidth, legendGroups.length)
  const margin = { top: legendLayout.top, right: 28, bottom: 44, left: 58 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const xExtent = extent(items, item => item.x); const yExtent = extent(items, item => item.y)
  const xMin = Math.min(0, xExtent[0] || 0)
  const xMax = (xExtent[1] || 1) * 1.08
  const xPadding = xMin >= 0 ? Math.max(1, xMax * .05) : 0
  const x = scaleLinear().domain([xMin - xPadding, xMax]).range([0, innerWidth])
  const y = scaleLinear().domain([Math.min(0, yExtent[0] || 0), (yExtent[1] || 1) * 1.12]).nice().range([innerHeight, 0])
  const maxSize = max(items, item => item.size) || 1
  const groupIndex = new Map(groups.map((group, index) => [group, index]))
  const color = scaleOrdinal(groups, chartTheme.palette)
  const gapValues = items
    .map(item => typeof item.y === 'number' && typeof item.cost === 'number' ? item.y - item.cost : null)
    .filter(value => value != null && Number.isFinite(value))
  const gapExtent = extent(gapValues)
  const gapColor = scaleLinear()
    .domain(gapExtent[0] === gapExtent[1] ? [gapExtent[0] || 0, (gapExtent[1] || 0) + 1] : [gapExtent[0] || 0, gapExtent[1] || 1])
    .range([chartTheme.palette[1], chartTheme.negative])
    .clamp(true)
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  styleAxis(root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).ticks(6).tickFormat(short).tickSize(-innerHeight)))
  styleAxis(root.append('g').call(axisLeft(y).ticks(5).tickFormat(short).tickSize(-innerWidth)))
  const points = root.selectAll('.d3-bubble').data(items).join('circle').attr('class', 'd3-mark d3-bubble')
    .attr('cx', item => {
      const offset = scatterPointOffset(groupIndex.get(String(item.group)), groups.length)
      return Math.max(0, Math.min(innerWidth, x(item.x) + offset))
    })
    .attr('cy', item => y(item.y)).attr('r', item => scatterPointRadius(item.size, maxSize))
    .attr('fill', item => {
      if (!isOverviewRelation) return color(String(item.group))
      const gap = typeof item.y === 'number' && typeof item.cost === 'number' ? item.y - item.cost : null
      return gap == null ? chartTheme.palette[1] : gapColor(gap)
    })
    .attr('fill-opacity', .82).attr('stroke', chartTheme.stroke).attr('stroke-width', 1.5)
  makeInteractive(points)
  if (isOverviewRelation) {
    const gradientId = `scatter-gap-${Math.random().toString(36).slice(2)}`
    const gradient = svg.append('defs').append('linearGradient').attr('id', gradientId)
    gradient.append('stop').attr('offset', '0%').attr('stop-color', chartTheme.palette[1])
    gradient.append('stop').attr('offset', '100%').attr('stop-color', chartTheme.negative)
    if (innerWidth < 420) {
      root.append('text').attr('x', 0).attr('y', -16).attr('fill', chartTheme.text).attr('font-size', 10).text('点大小 = 记录数 · 颜色 = 收费成本差')
    } else {
      root.append('text').attr('x', 0).attr('y', -16).attr('fill', chartTheme.text).attr('font-size', 10).text('点大小 = 记录数')
      const legendX = Math.max(150, innerWidth - 190)
      root.append('text').attr('x', legendX).attr('y', -16).attr('fill', chartTheme.text).attr('font-size', 10).text('颜色 = 收费成本差')
      root.append('rect').attr('x', legendX + 78).attr('y', -23).attr('width', 58).attr('height', 7).attr('rx', 3).attr('fill', `url(#${gradientId})`)
      root.append('text').attr('x', legendX + 140).attr('y', -16).attr('fill', chartTheme.text).attr('font-size', 9).text('暖色高')
    }
  } else {
    legendGroups.forEach((group, index) => {
      const column = index % legendLayout.columns
      const row = Math.floor(index / legendLayout.columns)
      const xPosition = column * legendLayout.cellWidth
      const yOffset = row * 18
      root.append('circle').attr('cx', xPosition + 5).attr('cy', -19 + yOffset).attr('r', 5).attr('fill', color(group))
      root.append('text').attr('x', xPosition + 14).attr('y', -16 + yOffset).attr('fill', chartTheme.text).attr('font-size', 10).text(visualLabel(group, 'severity'))
    })
    root.append('text').attr('x', innerWidth).attr('y', -16).attr('text-anchor', 'end').attr('fill', chartTheme.text).attr('font-size', 10).text('点大小 = 记录数')
  }
  root.append('text').attr('x', innerWidth).attr('y', innerHeight + 36).attr('text-anchor', 'end').attr('fill', chartTheme.text).attr('font-size', 10).text('平均住院时长（天）')
  root.append('text').attr('transform', `translate(-43,${innerHeight / 2}) rotate(-90)`).attr('text-anchor', 'middle').attr('fill', chartTheme.text).attr('font-size', 10).text('平均收费（美元）')
}

function drawHeatmap(svg, width, height, items) {
  const xLabels = [...new Set(items.map(item => item.x_label))]; const yLabels = [...new Set(items.map(item => item.y_label))]
  const margin = { top: 10, right: 22, bottom: 64, left: width < 430 ? 66 : 86 }
  const innerWidth = width - margin.left - margin.right; const innerHeight = height - margin.top - margin.bottom
  const x = scaleBand().domain(xLabels).range([0, innerWidth]).padding(.04); const y = scaleBand().domain(yLabels).range([0, innerHeight]).padding(.04)
  const maxValue = max(items, item => item.value) || 1; const color = scaleLinear().domain([0, maxValue]).range([chartTheme.heatLow, chartTheme.heatHigh])
  const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)
  const bottom = root.append('g').attr('transform', `translate(0,${innerHeight})`).call(axisBottom(x).tickSize(0).tickFormat(value => visualLabel(value, 'age'))); styleAxis(bottom, 12)
  bottom.selectAll('text').attr('transform', 'rotate(-22)').attr('text-anchor', 'end')
  styleAxis(root.append('g').call(axisLeft(y).tickSize(0).tickFormat(value => visualLabel(value, 'severity'))), 12)
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
    else if (props.presentation === 'correlation') drawCorrelation(svg, width, height, items)
    else drawBar(svg, width, height, items)
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
