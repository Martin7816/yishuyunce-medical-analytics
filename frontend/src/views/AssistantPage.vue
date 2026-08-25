<script setup>
import { nextTick, ref } from 'vue'
import { apiStreamRequest, getApiErrorMessage, isAbortError } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import { renderSafeMarkdown } from '../utils/markdown.js'

const MAX_QUESTION_LENGTH = 1000
const ALLOWED_CHART_TYPES = new Set(['bar', 'pie', 'table', 'status', 'grouped_bar', 'scatter', 'heatmap'])
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

const TOOL_LABELS = Object.freeze({
  get_dashboard_overview: '运营驾驶舱',
  get_hospital_overview: '医院运营',
  get_disease_overview: '疾病画像',
  get_cohort_summary: '住院群体',
  get_cost_overview: '费用与成本',
  get_risk_overview: '病情风险',
  get_payment_overview: '支付方式',
  get_model_metrics: '高费用模型',
})

const presets = Object.freeze([
  '概括当前运营情况',
  '费用与成本有哪些主要特征？',
  '疾病病例量排名如何？',
  '高费用模型表现如何？',
])

const quickActionMeta = Object.freeze([
  { label: '运营概览', description: '快速总结总体运营表现' },
  { label: '费用洞察', description: '分析收费与成本特征' },
  { label: '疾病分析', description: '查看主要疾病病例结构' },
  { label: '模型评估', description: '查看高费用模型表现' },
])

const question = ref('')
const result = ref(null)
const error = ref(null)
const questionError = ref('')
const loading = ref(false)
const lastQuestion = ref('')
const questionInput = ref(null)
const reportTitle = ref(null)
const errorPanel = ref(null)
const streamStage = ref(null)
let activeController = null

function createResultError(message) {
  const invalid = new Error(message)
  invalid.code = 'SERVICE_RESULT_INVALID'
  invalid.userMessage = message
  return invalid
}

function createPendingResult() {
  return {
    answer: '',
    tool_trace: [],
    sources: [],
    data_versions: [],
    chart: null,
    report: { title: 'AI 对话回复' },
    boundary: '',
    hasAnalyticsArtifacts: false,
  }
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeMetric(item) {
  if (!item || typeof item !== 'object') return null
  const key = normalizeText(item.key)
  const label = normalizeText(item.label)
  const value = item.value
  if (!label) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return { key, label, value, unit: normalizeText(item.unit) }
}

function normalizeSource(source) {
  if (!source || typeof source !== 'object') return null
  const tool = normalizeText(source.tool)
  const title = normalizeText(source.title)
  const dataVersion = normalizeText(source.data_version)
  const metrics = Array.isArray(source.metrics)
    ? source.metrics.map(normalizeMetric).filter(Boolean)
    : []
  if (!tool || !title || !dataVersion || !metrics.length) return null
  const sectionKeys = Array.isArray(source.sections)
    ? source.sections.map(section => normalizeText(section?.key)).filter(Boolean)
    : []
  return { tool, title, data_version: dataVersion, metrics, section_keys: sectionKeys }
}

function normalizeToolTrace(item) {
  if (!item || typeof item !== 'object') return null
  const tool = normalizeText(item.tool)
  const dataVersion = normalizeText(item.data_version)
  if (!tool || !dataVersion) return null
  return {
    tool,
    data_version: dataVersion,
    status: normalizeText(item.status) || 'success',
  }
}

function normalizeChartVisual(visual) {
  if (!visual || typeof visual !== 'object') return null
  const result = {}
  for (const key of ['question', 'x_label', 'y_label', 'unit']) {
    const value = normalizeText(visual[key])
    if (value) result[key] = value
  }

  if (Array.isArray(visual.legend)) {
    const legend = visual.legend.map(item => {
      if (!item || typeof item !== 'object') return null
      const key = normalizeText(item.key)
      const label = normalizeText(item.label)
      const style = normalizeText(item.style)
      if (!key || !label) return null
      return { key, label, ...(style ? { style } : {}) }
    }).filter(Boolean)
    if (legend.length) result.legend = legend
  }

  if (visual.summary && typeof visual.summary === 'object') {
    const summary = {}
    for (const key of ['text', 'source_section', 'data_version', 'generated_at', 'boundary']) {
      const value = normalizeText(visual.summary[key])
      if (value) summary[key] = value
    }
    if (typeof visual.summary.related_not_causal === 'boolean') {
      summary.related_not_causal = visual.summary.related_not_causal
    }
    if (Object.keys(summary).length) result.summary = summary
  }

  if (visual.fallback && typeof visual.fallback === 'object') {
    const fallback = {}
    const type = normalizeText(visual.fallback.type)
    if (type) fallback.type = type
    if (Array.isArray(visual.fallback.columns)) {
      const columns = visual.fallback.columns.map(normalizeText).filter(Boolean)
      if (columns.length) fallback.columns = columns
    }
    if (Object.keys(fallback).length) result.fallback = fallback
  }

  if (visual.empty && typeof visual.empty === 'object') {
    const empty = {}
    for (const key of ['title', 'text']) {
      const value = normalizeText(visual.empty[key])
      if (value) empty[key] = value
    }
    if (Object.keys(empty).length) result.empty = empty
  }

  return Object.keys(result).length ? result : null
}

function normalizeChartSimpleItems(items) {
  if (!Array.isArray(items)) return []
  return items.map(item => {
    if (!item || typeof item !== 'object') return null
    const name = normalizeText(item.name)
    const value = item.value
    if (!name || (typeof value !== 'number' && typeof value !== 'string')) return null
    if (typeof value === 'number' && !Number.isFinite(value)) return null
    return { name, value }
  }).filter(Boolean)
}

function normalizeGroupedBarItems(items) {
  if (!Array.isArray(items)) return []
  return items.map(item => {
    if (!item || typeof item !== 'object') return null
    const category = normalizeText(item.category)
    if (!category || !Array.isArray(item.series)) return null
    const series = item.series.map(point => {
      if (!point || typeof point !== 'object') return null
      const key = normalizeText(point.key)
      const label = normalizeText(point.label)
      const value = point.value
      if (!key || !label || typeof value !== 'number' || !Number.isFinite(value)) return null
      return { key, label, value }
    }).filter(Boolean)
    return series.length ? { category, series } : null
  }).filter(Boolean)
}

function normalizeScatterItems(items) {
  if (!Array.isArray(items)) return []
  return items.map(item => {
    if (!item || typeof item !== 'object') return null
    const name = normalizeText(item.name)
    if (!name || typeof item.x !== 'number' || !Number.isFinite(item.x) || typeof item.y !== 'number' || !Number.isFinite(item.y)) return null
    const normalized = { name, x: item.x, y: item.y }
    if (typeof item.group === 'string' && item.group.trim()) normalized.group = item.group.trim()
    for (const key of ['size', 'cost', 'high_cost_rate']) {
      if (typeof item[key] === 'number' && Number.isFinite(item[key])) normalized[key] = item[key]
    }
    return normalized
  }).filter(Boolean)
}

function normalizeHeatmapItems(items) {
  if (!Array.isArray(items)) return []
  return items.map(item => {
    if (!item || typeof item !== 'object') return null
    const xLabel = normalizeText(item.x_label)
    const yLabel = normalizeText(item.y_label)
    if (!xLabel || !yLabel || typeof item.value !== 'number' || !Number.isFinite(item.value)) return null
    const normalized = { x_label: xLabel, y_label: yLabel, value: item.value }
    const unit = normalizeText(item.unit)
    if (unit) normalized.unit = unit
    for (const key of ['numerator', 'denominator', 'high_risk_rate']) {
      if (typeof item[key] === 'number' && Number.isFinite(item[key])) normalized[key] = item[key]
    }
    return normalized
  }).filter(Boolean)
}

function normalizeChart(chart) {
  if (!chart || typeof chart !== 'object') return null
  const type = normalizeText(chart.type)
  const title = normalizeText(chart.title)
  if (!ALLOWED_CHART_TYPES.has(type) || !title || !Array.isArray(chart.items)) return null
  const items = type === 'grouped_bar'
    ? normalizeGroupedBarItems(chart.items)
    : type === 'scatter'
      ? normalizeScatterItems(chart.items)
      : type === 'heatmap'
        ? normalizeHeatmapItems(chart.items)
        : normalizeChartSimpleItems(chart.items)
  if (!items.length) return null
  const sourceSection = normalizeText(chart.source_section)
  const sourceTool = normalizeText(chart.source_tool)
  const dataVersion = normalizeText(chart.data_version)
  const sourceMetricKeys = Array.isArray(chart.source_metric_keys)
    ? chart.source_metric_keys.map(normalizeText).filter(Boolean)
    : []
  const visual = normalizeChartVisual(chart.visual)
  return {
    type,
    title,
    items,
    ...(sourceSection ? { source_section: sourceSection } : {}),
    ...(sourceTool ? { source_tool: sourceTool } : {}),
    ...(dataVersion ? { data_version: dataVersion } : {}),
    ...(sourceMetricKeys.length ? { source_metric_keys: sourceMetricKeys } : {}),
    ...(visual ? { visual } : {}),
  }
}

function buildSafeChart(source) {
  return {
    type: 'bar',
    title: `${source.title}来源指标`,
    items: source.metrics.slice(0, 8).map(metric => ({
      name: metric.label,
      value: metric.value,
    })),
    source_tool: source.tool,
    data_version: source.data_version,
    source_metric_keys: source.metrics.map(metric => metric.key).filter(Boolean),
  }
}

function normalizePayload(payload) {
  const answer = normalizeText(payload?.answer)
  const rawToolTraceValue = payload?.tool_trace
  const rawSourcesValue = payload?.sources
  const rawDataVersionsValue = payload?.data_versions
  const rawToolTrace = Array.isArray(rawToolTraceValue) ? rawToolTraceValue : []
  const rawSources = Array.isArray(rawSourcesValue) ? rawSourcesValue : []
  const rawDataVersions = Array.isArray(rawDataVersionsValue) ? rawDataVersionsValue : []
  const hasSources = rawSources.length > 0
  const hasToolTrace = rawToolTrace.length > 0
  const hasVersions = rawDataVersions.length > 0
  const hasChart = payload?.chart != null
  const hasMalformedEvidenceCollections = [
    rawToolTraceValue,
    rawSourcesValue,
    rawDataVersionsValue,
  ].some(value => value != null && !Array.isArray(value))
  const hasAnalyticsArtifacts =
    hasSources
    || hasToolTrace
    || hasVersions
    || hasChart
    || hasMalformedEvidenceCollections
  const toolTrace = rawToolTrace.map(normalizeToolTrace).filter(Boolean)
  const sources = rawSources.map(normalizeSource).filter(Boolean)
  const dataVersions = rawDataVersions.map(normalizeText).filter(Boolean)
  const boundary = normalizeText(payload?.boundary)

  if (!answer || !boundary) {
    throw createResultError('当前回答缺少可核验来源，未展示回答。请重试。')
  }

  if (!hasAnalyticsArtifacts) {
    return {
      answer,
      tool_trace: [],
      sources: [],
      data_versions: [],
      chart: null,
      report: { title: 'AI 对话回复' },
      boundary,
      hasAnalyticsArtifacts: false,
    }
  }

  if (
    toolTrace.length < 1
    || toolTrace.length > 2
    || sources.length < 1
    || sources.length > 2
    || !dataVersions.length
    || toolTrace.length !== rawToolTrace.length
    || sources.length !== rawSources.length
    || dataVersions.length !== rawDataVersions.length
  ) {
    throw createResultError('当前回答缺少可核验来源，未展示回答。请重试。')
  }

  const sourceVersions = new Set(sources.map(source => source.data_version))
  const traceVersions = new Set(toolTrace.map(trace => trace.data_version))
  if (
    [...sourceVersions].some(version => !dataVersions.includes(version))
    || [...traceVersions].some(version => !dataVersions.includes(version))
  ) {
    throw createResultError('当前回答的来源版本无法核对，未展示回答。请重试。')
  }

  const normalizedChart = normalizeChart(payload.chart)
  const sourceSectionKeys = sources.flatMap(source => source.section_keys || [])
  if (
    normalizedChart?.data_version
    && !dataVersions.includes(normalizedChart.data_version)
  ) {
    throw createResultError('当前回答的图表来源版本无法核对，未展示回答。请重试。')
  }
  if (
    normalizedChart?.source_tool
    && !sources.some(source => source.tool === normalizedChart.source_tool)
  ) {
    throw createResultError('当前回答的图表来源工具无法核对，未展示回答。请重试。')
  }
  if (
    normalizedChart?.source_section
    && sourceSectionKeys.length
    && !sourceSectionKeys.includes(normalizedChart.source_section)
  ) {
    throw createResultError('当前回答的图表来源 section 无法核对，未展示回答。请重试。')
  }
  const safeChart = normalizedChart || buildSafeChart(sources[0])
  return {
    answer,
    tool_trace: toolTrace,
    sources,
    data_versions: [...new Set(dataVersions)],
    chart: safeChart,
    report: { title: normalizeText(payload?.report?.title) || '医数云策洞察简报' },
    boundary,
    hasAnalyticsArtifacts: true,
  }
}

function validateQuestion(value) {
  if (!value) return '请输入问题后再提交。'
  if (value.length > MAX_QUESTION_LENGTH) return `问题不能超过 ${MAX_QUESTION_LENGTH} 个字符。`
  return ''
}

function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
      continue
    }
    throw createResultError('流式响应格式无效，未展示回答。请重试。')
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch (caught) {
    throw createResultError('流式响应格式无效，未展示回答。请重试。')
  }
}

async function* readSseEvents(reader) {
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  while (!finished) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    buffer = buffer.replace(/\r\n/g, '\n')
    let boundaryIndex = buffer.indexOf('\n\n')
    while (boundaryIndex >= 0) {
      const block = buffer.slice(0, boundaryIndex).replace(/\r$/, '')
      buffer = buffer.slice(boundaryIndex + 2)
      const parsed = parseSseBlock(block)
      if (parsed) yield parsed
      boundaryIndex = buffer.indexOf('\n\n')
    }
    finished = done
  }
  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer.replace(/\r$/, ''))
    if (parsed) yield parsed
  }
}

function createStreamError(data) {
  const code = normalizeText(data?.code) || 'UPSTREAM_SERVICE_ERROR'
  const message = normalizeText(data?.message) || getApiErrorMessage({ code })
  const streamError = new Error(message)
  streamError.code = code
  streamError.userMessage = message
  streamError.traceId = normalizeText(data?.trace_id)
  return streamError
}

function updateStreamStage(data) {
  if (!data || typeof data !== 'object' || !normalizeText(data.stage) || !normalizeText(data.label)) {
    throw createResultError('流式阶段状态无效，未展示回答。请重试。')
  }
  streamStage.value = {
    stage: normalizeText(data.stage),
    label: normalizeText(data.label),
  }
}

async function consumeStream(text, controller) {
  const response = await apiStreamRequest('/ai/chat/stream', {
    method: 'POST',
    body: JSON.stringify({ message: text }),
    signal: controller.signal,
  })
  const reader = response.body.getReader()
  let answer = ''
  let receivedDone = false

  for await (const event of readSseEvents(reader)) {
    if (receivedDone) throw createResultError('流式结果重复完成，未展示回答。请重试。')
    if (event.event === 'stage') {
      updateStreamStage(event.data)
      continue
    }
    if (event.event === 'delta') {
      if (!event.data || typeof event.data.text !== 'string') {
        throw createResultError('流式回答内容无效，未展示回答。请重试。')
      }
      answer += event.data.text
      if (result.value) result.value = { ...result.value, answer }
      continue
    }
    if (event.event === 'error') throw createStreamError(event.data)
    if (event.event === 'done') {
      if (!event.data || typeof event.data !== 'object') {
        throw createResultError('流式结果缺少安全元数据，未展示回答。请重试。')
      }
      const finalAnswer = answer || normalizeText(event.data.answer)
      result.value = normalizePayload({ ...event.data, answer: finalAnswer })
      streamStage.value = { stage: 'complete', label: '分析完成' }
      receivedDone = true
      continue
    }
    throw createResultError('流式事件类型无效，未展示回答。请重试。')
  }

  if (!receivedDone) throw createResultError('流式回答未正常完成，请重试。')
}

async function ask(value = question.value) {
  const text = typeof value === 'string' ? value.trim() : ''
  questionError.value = validateQuestion(text)
  if (questionError.value) {
    await nextTick()
    questionInput.value?.focus()
    return
  }

  lastQuestion.value = text
  question.value = text
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  result.value = createPendingResult()
  error.value = null
  questionError.value = ''
  streamStage.value = { stage: 'preparing', label: '正在准备回答' }
  try {
    await consumeStream(text, controller)
    await nextTick()
    reportTitle.value?.focus()
  } catch (caught) {
    if (isAbortError(caught) || controller.signal.aborted) {
      if (result.value?.answer) {
        streamStage.value = { stage: 'stopped', label: '已停止生成，可重新提问' }
      } else {
        result.value = null
        streamStage.value = null
      }
    } else if (result.value?.answer) {
      streamStage.value = { stage: 'interrupted', label: '生成中断，可重新提问' }
    } else {
      result.value = null
      error.value = caught
      await nextTick()
      errorPanel.value?.focus()
    }
  } finally {
    loading.value = false
    if (activeController === controller) activeController = null
  }
}

function stopGeneration() {
  activeController?.abort()
}

function submitForm() {
  if (loading.value) stopGeneration()
  else ask()
}

function choose(value) {
  ask(value)
}

function retry() {
  ask(lastQuestion.value || question.value)
}

function printReport() {
  window.print()
}

function toolLabel(tool) {
  return TOOL_LABELS[tool] || '分析工具'
}

function toolStatus(status) {
  return status === 'success' ? '已读取并记录来源' : '未完成'
}

function formatMetric(metric) {
  if (metric.value == null) return '—'
  if (typeof metric.value !== 'number') return metric.value
  if (metric.unit === '%') return `${number.format(metric.value * 100)}%`
  return `${number.format(metric.value)}${metric.unit || ''}`
}

function errorMessage(caught) {
  return caught?.userMessage || getApiErrorMessage(caught)
}
</script>

<template>
  <div class="page-wrap assistant-page">
    <header class="assistant-hero">
      <div class="assistant-hero-copy">
        <div class="assistant-product-lockup" aria-label="AI Insight Engine，由 DeepSeek 提供支持">
          <span class="assistant-product-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 3.5 19 7v5.2c0 4-2.3 6.8-7 8.3-4.7-1.5-7-4.3-7-8.3V7l7-3.5Z" /><path d="M8.5 12h7M12 8.5v7" /></svg>
          </span>
          <span>
            <strong>AI Insight Engine</strong>
            <small>Powered by DeepSeek</small>
          </span>
        </div>
        <p class="eyebrow assistant-hero-eyebrow">医疗运营智能分析工作台</p>
        <h1 id="page-title" data-page-title tabindex="-1">AI 医疗运营洞察</h1>
        <p class="assistant-hero-description">基于已发布的医疗运营数据，快速获得可追溯、可核验的分析结论。</p>
        <div class="assistant-capabilities" aria-label="分析能力">
          <div class="assistant-capability">
            <span class="assistant-capability-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M5 5h14v14H5zM8 9h8M8 12h8M8 15h5" /></svg>
            </span>
            <span><strong>只读汇总数据</strong><small>基于已发布快照</small></span>
          </div>
          <div class="assistant-capability">
            <span class="assistant-capability-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M4 6.5h16M4 12h16M4 17.5h16" /><circle cx="8" cy="6.5" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="17.5" r="2" /></svg>
            </span>
            <span><strong>白名单分析工具</strong><small>调用范围受控</small></span>
          </div>
          <div class="assistant-capability">
            <span class="assistant-capability-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M7 4h10v16H7zM10 8h4M10 12h4M10 16h2" /><path d="M5 7H3v14h10v-2" /></svg>
            </span>
            <span><strong>来源与版本可追溯</strong><small>结果可复核</small></span>
          </div>
        </div>
        <div class="assistant-trust-line" aria-label="安全边界">
          <span class="assistant-trust-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 3 20 7v5c0 4.1-2.8 7.2-8 9-5.2-1.8-8-4.9-8-9V7l8-4Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></svg>
          </span>
          <span><strong>安全边界</strong> 仅分析群体汇总数据，不访问患者级明细，不执行自由 SQL。</span>
        </div>
      </div>
      <div class="assistant-hero-visual" aria-hidden="true">
        <div class="assistant-visual-grid"></div>
        <svg class="assistant-visual-svg" viewBox="0 0 420 300" focusable="false">
          <defs>
            <radialGradient id="assistant-core-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0" stop-color="#BFDBFE" stop-opacity=".8" />
              <stop offset=".55" stop-color="#60A5FA" stop-opacity=".28" />
              <stop offset="1" stop-color="#4F46E5" stop-opacity="0" />
            </radialGradient>
            <linearGradient id="assistant-orbit-stroke" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stop-color="#38BDF8" stop-opacity=".12" />
              <stop offset=".5" stop-color="#93C5FD" stop-opacity=".86" />
              <stop offset="1" stop-color="#818CF8" stop-opacity=".18" />
            </linearGradient>
          </defs>
          <circle class="assistant-visual-glow" cx="215" cy="148" r="112" fill="url(#assistant-core-glow)" />
          <ellipse class="assistant-visual-orbit assistant-visual-orbit-one" cx="215" cy="148" rx="126" ry="52" />
          <ellipse class="assistant-visual-orbit assistant-visual-orbit-two" cx="215" cy="148" rx="72" ry="126" />
          <path class="assistant-visual-connector" d="m105 90 62 32m99-56-46 56m95 75-64-40m-93 65 42-55" />
          <circle class="assistant-visual-node node-one" cx="105" cy="90" r="5" />
          <circle class="assistant-visual-node node-two" cx="266" cy="66" r="4" />
          <circle class="assistant-visual-node node-three" cx="330" cy="205" r="5" />
          <circle class="assistant-visual-node node-four" cx="122" cy="240" r="4" />
          <circle class="assistant-visual-core" cx="215" cy="148" r="42" />
          <path class="assistant-visual-core-mark" d="M198 148h34M215 131v34" />
        </svg>
        <div class="assistant-visual-label"><span>数据可信</span><strong>结果可核验</strong></div>
      </div>
    </header>

    <section class="assistant-composer-shell" :aria-busy="loading" aria-labelledby="assistant-question-title">
      <div class="assistant-composer-heading">
        <div>
          <p class="assistant-section-kicker">开始一次分析</p>
          <h2 id="assistant-question-title">你想了解什么？</h2>
        </div>
        <span class="assistant-single-turn"><span aria-hidden="true"></span>单轮分析</span>
      </div>

      <form class="assistant-form" @submit.prevent="submitForm">
        <div class="assistant-input-surface" :class="{ 'has-error': questionError }">
          <label for="assistant-question" class="assistant-question-label">分析问题</label>
          <textarea
            id="assistant-question"
            ref="questionInput"
            v-model="question"
            class="assistant-textarea"
            :maxlength="MAX_QUESTION_LENGTH"
            rows="4"
            autocomplete="off"
            spellcheck="false"
            aria-describedby="assistant-question-help assistant-question-error"
            :aria-invalid="Boolean(questionError)"
            placeholder="向 AI 询问医院、疾病、费用、风险或运营问题…"
            @keydown.ctrl.enter.prevent="submitForm"
            @keydown.meta.enter.prevent="submitForm"
          ></textarea>
          <div class="assistant-composer-footer">
            <div class="assistant-scope-control" aria-label="数据分析范围：已发布群体汇总">
              <span class="assistant-scope-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M5 5h14v14H5zM8 9h8M8 12h8M8 15h5" /></svg>
              </span>
              <span class="assistant-scope-label">数据分析范围</span>
              <span class="assistant-scope-value">已发布群体汇总</span>
            </div>
            <div class="assistant-composer-meta">
              <span class="assistant-counter" aria-live="polite">{{ question.length }}/{{ MAX_QUESTION_LENGTH }}</span>
              <span id="assistant-question-help" class="assistant-help">Ctrl/⌘ + Enter 提交</span>
            </div>
            <button
              type="submit"
              class="primary-button assistant-submit"
              :aria-label="loading ? '停止生成' : '发送问题'"
            >
              <span v-if="loading" class="assistant-submit-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4.5 14-3.2-5.2L5 12Zm6.3 1.8L19 5" /></svg>
              <span>{{ loading ? '停止生成' : '发送' }}</span>
            </button>
          </div>
        </div>
        <p id="assistant-question-error" class="assistant-question-error" role="alert">{{ questionError }}</p>
        <div v-if="loading" class="assistant-loading-note" role="status" aria-live="polite">
          <span class="assistant-loading-pulse" aria-hidden="true"><i></i><i></i><i></i></span>
          <span>{{ streamStage?.label || '正在连接 AI 服务，请稍候。' }}</span>
        </div>
      </form>
    </section>

    <section class="assistant-quick-actions" aria-labelledby="assistant-quick-actions-title">
      <div class="assistant-quick-heading">
        <div>
          <p class="assistant-section-kicker">快速开始</p>
          <h2 id="assistant-quick-actions-title">从一个常见分析开始</h2>
        </div>
        <p>选择一个方向，分析助手会直接带入问题。</p>
      </div>
      <div class="assistant-quick-grid" aria-label="预设问题">
        <button
          v-for="(preset, index) in presets"
          :key="preset"
          type="button"
          class="assistant-quick-card"
          :class="`accent-${index + 1}`"
          :disabled="loading"
          @click="choose(preset)"
        >
          <span class="assistant-quick-card-top">
            <span class="assistant-quick-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13m-5-5 5 5-5 5" /></svg>
          </span>
          <strong>{{ quickActionMeta[index].label }}</strong>
          <span>{{ quickActionMeta[index].description }}</span>
        </button>
      </div>
    </section>

    <section
      v-if="error"
      ref="errorPanel"
      class="assistant-error-panel"
      role="alert"
      tabindex="-1"
      aria-labelledby="assistant-error-title"
    >
      <div class="assistant-state-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 21 20H3L12 3Zm0 6v5m0 3h.01" /></svg></div>
      <div>
        <p class="assistant-section-kicker">本次提问未完成</p>
        <h2 id="assistant-error-title">AI 服务未能完成回答</h2>
        <p class="assistant-error-message">{{ errorMessage(error) }}</p>
        <div class="assistant-error-meta">
          <span v-if="error.code">错误类型：<code>{{ error.code }}</code></span>
          <span v-if="error.traceId">追踪编号：<code>{{ error.traceId }}</code></span>
        </div>
        <button type="button" class="primary-button assistant-retry" @click="retry">重新提问</button>
      </div>
    </section>

    <article
      v-if="result"
      class="answer-sheet assistant-report"
      aria-labelledby="assistant-report-title"
    >
      <div
        v-if="streamStage"
        class="assistant-stream-status"
        :class="`is-${streamStage.stage}`"
        :role="streamStage.stage === 'interrupted' ? 'alert' : 'status'"
        aria-live="polite"
      >
        <span class="assistant-stream-status-dot" aria-hidden="true"></span>
        <span>{{ streamStage.label }}</span>
      </div>
      <header class="assistant-report-header">
        <div class="assistant-report-heading-copy">
          <p class="assistant-report-overline"><span aria-hidden="true"></span>{{ result.hasAnalyticsArtifacts ? 'AI 洞察报告' : 'AI 对话回复' }}</p>
          <h2 id="assistant-report-title" ref="reportTitle" tabindex="-1">{{ result.report.title }}</h2>
          <p v-if="result.hasAnalyticsArtifacts">回答已通过来源与数据版本核验，正文按纯文本展示。</p>
          <p v-else>这是一条普通交流回复，未使用分析数据。</p>
        </div>
        <div class="assistant-report-actions">
          <span v-if="result.hasAnalyticsArtifacts" class="assistant-verified-badge"><span aria-hidden="true">✓</span>已核验</span>
          <button type="button" class="assistant-print-button" @click="printReport">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9V4h12v5M6 17H4a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-2M6 14h12v7H6z" /></svg>
            <span>打印 / 导出 PDF</span>
          </button>
        </div>
      </header>

      <div class="assistant-report-body">
        <section class="assistant-report-section assistant-answer-section" aria-labelledby="assistant-answer-title">
        <div class="assistant-section-heading">
          <div>
              <p class="assistant-section-kicker">先看结论</p>
              <h3 id="assistant-answer-title">{{ result.hasAnalyticsArtifacts ? 'AI 分析回答' : 'AI 回复' }}</h3>
          </div>
            <span v-if="result.hasAnalyticsArtifacts" class="assistant-plain-text-badge">纯文本回答</span>
        </div>
        <div class="answer-text answer-markdown" v-html="renderSafeMarkdown(result.answer)"></div>
        </section>

        <section v-if="result.hasAnalyticsArtifacts" class="assistant-report-section assistant-chart-section" aria-labelledby="assistant-chart-title">
        <div class="assistant-section-heading">
          <div>
              <p class="assistant-section-kicker">关键指标</p>
              <h3 id="assistant-chart-title">数据分析视图</h3>
          </div>
            <span class="assistant-plain-text-badge">白名单图表</span>
        </div>
          <p class="assistant-chart-title">{{ result.chart.title }}</p>
        <p v-if="result.chart.source_section || result.chart.data_version" class="assistant-chart-provenance">
          证据 section：<code>{{ result.chart.source_section || 'metrics' }}</code>
          <span v-if="result.chart.data_version"> · 数据版本：<code>{{ result.chart.data_version }}</code></span>
        </p>
        <div class="assistant-chart-frame">
          <AnalyticsChart :section="result.chart" />
        </div>
          <p class="assistant-chart-note">图表只使用来源指标中的名称和值，不执行模型返回的脚本或图表配置。</p>
        </section>

        <section v-if="result.hasAnalyticsArtifacts" class="assistant-report-section assistant-sources-section" aria-labelledby="assistant-sources-title">
        <div class="assistant-section-heading">
          <div>
              <p class="assistant-section-kicker">可复核数据</p>
              <h3 id="assistant-sources-title">可信来源</h3>
          </div>
            <span class="assistant-count-badge">{{ result.sources.length }} 个来源</span>
        </div>
        <div class="assistant-source-grid">
          <article v-for="source in result.sources" :key="`${source.tool}-${source.data_version}`" class="source-block assistant-source-block">
            <header class="assistant-source-header">
              <div>
                <h4>{{ source.title }}</h4>
                <p>{{ toolLabel(source.tool) }}</p>
              </div>
                <span class="assistant-source-status"><span aria-hidden="true">✓</span>已核验</span>
            </header>
            <ul class="assistant-metric-list">
              <li v-for="metric in source.metrics" :key="metric.label">
                <span>{{ metric.label }}</span>
                <strong>{{ formatMetric(metric) }}</strong>
              </li>
            </ul>
            <p class="assistant-source-version"><span>数据版本</span><code>{{ source.data_version }}</code></p>
          </article>
        </div>
        </section>

        <section v-if="result.hasAnalyticsArtifacts" class="assistant-report-section assistant-trace-section" aria-labelledby="assistant-trace-title">
          <div class="assistant-section-heading">
            <div>
              <p class="assistant-section-kicker">可追溯过程</p>
              <h3 id="assistant-trace-title">工具执行过程</h3>
            </div>
            <span class="assistant-count-badge">{{ result.tool_trace.length }} 次调用</span>
          </div>
          <ol class="tool-trace assistant-tool-trace" aria-label="白名单工具调用时间线">
            <li v-for="(item, index) in result.tool_trace" :key="`${item.tool}-${index}`">
              <span class="assistant-trace-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="assistant-trace-content">
                <strong>{{ toolLabel(item.tool) }}</strong>
                <span class="assistant-trace-status" :class="{ 'is-incomplete': item.status !== 'success' }"><span aria-hidden="true">{{ item.status === 'success' ? '✓' : '!' }}</span>{{ toolStatus(item.status) }}</span>
                <small>工具：{{ item.tool }}</small>
                <code>数据版本：{{ item.data_version }}</code>
              </div>
            </li>
          </ol>
        </section>
      </div>

      <footer class="data-footer assistant-report-footer">
        <div class="assistant-safety-note">
          <span class="assistant-safety-note-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 3 20 7v5c0 4.1-2.8 7.2-8 9-5.2-1.8-8-4.9-8-9V7l8-4Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></svg>
          </span>
          <div>
            <strong>安全与可追溯</strong>
            <span>仅分析群体汇总数据 · 不访问患者级明细 · 不执行自由 SQL · 数据来源可追踪</span>
          </div>
        </div>
        <div v-if="result.boundary" class="assistant-boundary">
          <strong>统计边界</strong>
          <span>{{ result.boundary }}</span>
        </div>
        <div v-if="result.hasAnalyticsArtifacts" class="assistant-versions">
          <strong>报告数据版本</strong>
          <code v-for="version in result.data_versions" :key="version">{{ version }}</code>
        </div>
      </footer>
    </article>
  </div>
</template>
