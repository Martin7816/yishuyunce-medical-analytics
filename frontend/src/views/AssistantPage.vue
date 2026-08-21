<script setup>
import { nextTick, ref } from 'vue'
import { apiRequest, getApiErrorMessage } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'

const MAX_QUESTION_LENGTH = 1000
const ALLOWED_CHART_TYPES = new Set(['bar', 'pie', 'table', 'status'])
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

const question = ref('请概括当前运营情况，并说明引用的数据版本。')
const result = ref(null)
const error = ref(null)
const questionError = ref('')
const loading = ref(false)
const lastQuestion = ref('')
const questionInput = ref(null)
const reportTitle = ref(null)
const errorPanel = ref(null)

function createResultError(message) {
  const invalid = new Error(message)
  invalid.code = 'SERVICE_RESULT_INVALID'
  invalid.userMessage = message
  return invalid
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeMetric(item) {
  if (!item || typeof item !== 'object') return null
  const label = normalizeText(item.label)
  const value = item.value
  if (!label) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return { label, value, unit: normalizeText(item.unit) }
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
  return { tool, title, data_version: dataVersion, metrics }
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

function normalizeChart(chart) {
  if (!chart || typeof chart !== 'object') return null
  const type = normalizeText(chart.type)
  const title = normalizeText(chart.title)
  if (!ALLOWED_CHART_TYPES.has(type) || !title || !Array.isArray(chart.items)) return null
  const items = chart.items
    .map(item => {
      if (!item || typeof item !== 'object') return null
      const name = normalizeText(item.name)
      const value = item.value
      if (!name || (typeof value !== 'number' && typeof value !== 'string')) return null
      if (typeof value === 'number' && !Number.isFinite(value)) return null
      return { name, value }
    })
    .filter(Boolean)
  return items.length ? { type, title, items } : null
}

function buildSafeChart(source) {
  return {
    type: 'bar',
    title: `${source.title}来源指标`,
    items: source.metrics.slice(0, 8).map(metric => ({
      name: metric.label,
      value: metric.value,
    })),
  }
}

function normalizePayload(payload) {
  const answer = normalizeText(payload?.answer)
  const rawToolTrace = Array.isArray(payload?.tool_trace) ? payload.tool_trace : []
  const rawSources = Array.isArray(payload?.sources) ? payload.sources : []
  const rawDataVersions = Array.isArray(payload?.data_versions) ? payload.data_versions : []
  const toolTrace = rawToolTrace.map(normalizeToolTrace).filter(Boolean)
  const sources = rawSources.map(normalizeSource).filter(Boolean)
  const dataVersions = rawDataVersions.map(normalizeText).filter(Boolean)
  const boundary = normalizeText(payload?.boundary)
  if (
    !answer
    || toolTrace.length < 1
    || toolTrace.length > 2
    || sources.length < 1
    || sources.length > 2
    || !dataVersions.length
    || toolTrace.length !== rawToolTrace.length
    || sources.length !== rawSources.length
    || dataVersions.length !== rawDataVersions.length
    || !boundary
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

  const safeChart = normalizeChart(payload.chart) || buildSafeChart(sources[0])
  return {
    answer,
    tool_trace: toolTrace,
    sources,
    data_versions: [...new Set(dataVersions)],
    chart: safeChart,
    report: { title: normalizeText(payload?.report?.title) || '医数云策洞察简报' },
    boundary,
  }
}

function validateQuestion(value) {
  if (!value) return '请输入问题后再提交。'
  if (value.length > MAX_QUESTION_LENGTH) return `问题不能超过 ${MAX_QUESTION_LENGTH} 个字符。`
  return ''
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
  loading.value = true
  result.value = null
  error.value = null
  questionError.value = ''
  try {
    const payload = await apiRequest('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text }),
    })
    result.value = normalizePayload(payload)
    await nextTick()
    reportTitle.value?.focus()
  } catch (caught) {
    error.value = caught
    await nextTick()
    errorPanel.value?.focus()
  } finally {
    loading.value = false
  }
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
    <header class="page-heading assistant-heading">
      <div>
        <p class="eyebrow">DeepSeek · 白名单分析工具</p>
        <h1 id="page-title" data-page-title tabindex="-1">AI 问答与洞察报告</h1>
        <p>回答只读取已发布的群体汇总快照，不执行 SQL、不访问患者明细，也不保存多轮历史。</p>
        <div class="assistant-constraints" aria-label="AI 使用边界">
          <span>只读汇总指标</span>
          <span>最多两次工具调用</span>
          <span>来源与版本可追踪</span>
        </div>
      </div>
    </header>

    <section class="ask-card assistant-ask-card" :aria-busy="loading" aria-labelledby="assistant-question-title">
      <div class="assistant-card-heading">
        <div>
          <p class="assistant-section-kicker">先选一个问题，或输入自己的问题</p>
          <h2 id="assistant-question-title">向分析助手提问</h2>
        </div>
        <span class="assistant-card-note">单轮提问</span>
      </div>

      <div class="preset-row" aria-label="预设问题">
        <button
          v-for="preset in presets"
          :key="preset"
          type="button"
          class="preset-button"
          :disabled="loading"
          @click="choose(preset)"
        >
          {{ preset }}
        </button>
      </div>

      <form class="assistant-form" @submit.prevent="ask()">
        <label for="assistant-question" class="assistant-question-label">分析问题</label>
        <textarea
          id="assistant-question"
          ref="questionInput"
          v-model="question"
          class="assistant-textarea"
          :class="{ 'has-error': questionError }"
          :maxlength="MAX_QUESTION_LENGTH"
          rows="4"
          autocomplete="off"
          spellcheck="false"
          aria-describedby="assistant-question-help assistant-question-error"
          :aria-invalid="Boolean(questionError)"
          placeholder="例如：比较费用与成本的主要特征。"
          @keydown.ctrl.enter.prevent="ask()"
          @keydown.meta.enter.prevent="ask()"
        ></textarea>
        <div class="assistant-form-footer">
          <div>
            <p id="assistant-question-help" class="assistant-help">支持 1—1000 个字符；Ctrl/⌘ + Enter 可提交。</p>
            <p id="assistant-question-error" class="assistant-question-error" role="alert">{{ questionError }}</p>
          </div>
          <span class="assistant-counter" aria-live="polite">{{ question.length }}/{{ MAX_QUESTION_LENGTH }}</span>
          <button type="submit" class="primary-button assistant-submit" :disabled="loading">
            {{ loading ? '正在调用分析工具…' : '提交问题' }}
          </button>
        </div>
        <p v-if="loading" class="loading-note assistant-loading-note" role="status" aria-live="polite">正在调用白名单分析工具，请稍候。</p>
      </form>
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
      <header class="assistant-report-header">
        <div>
          <p class="eyebrow">已核验来源 · 可打印报告</p>
          <h2 id="assistant-report-title" ref="reportTitle" tabindex="-1">{{ result.report.title }}</h2>
          <p>以下内容由白名单分析工具提供汇总指标，回答正文按纯文本展示。</p>
        </div>
        <button type="button" class="assistant-print-button" @click="printReport">打印 / 导出 PDF</button>
      </header>

      <section class="assistant-report-section assistant-answer-section" aria-labelledby="assistant-answer-title">
        <div class="assistant-section-heading">
          <div>
            <p class="assistant-section-kicker">回答正文</p>
            <h3 id="assistant-answer-title">分析回答</h3>
          </div>
          <span class="assistant-plain-text-badge">纯文本</span>
        </div>
        <p class="answer-text">{{ result.answer }}</p>
      </section>

      <section class="assistant-report-section assistant-chart-section" aria-labelledby="assistant-chart-title">
        <div class="assistant-section-heading">
          <div>
            <p class="assistant-section-kicker">来源指标的预定义视图</p>
            <h3 id="assistant-chart-title">指标概览</h3>
          </div>
          <span class="assistant-plain-text-badge">白名单图表</span>
        </div>
        <div class="assistant-chart-frame">
          <AnalyticsChart :section="result.chart" />
        </div>
        <p class="assistant-chart-note">图表只使用来源指标中的名称和值，不执行模型返回的脚本或图表配置。</p>
      </section>

      <section class="assistant-report-section" aria-labelledby="assistant-trace-title">
        <div class="assistant-section-heading">
          <div>
            <p class="assistant-section-kicker">调用记录</p>
            <h3 id="assistant-trace-title">工具执行过程</h3>
          </div>
          <span class="assistant-count-badge">{{ result.tool_trace.length }} 次</span>
        </div>
        <ol class="tool-trace assistant-tool-trace">
          <li v-for="(item, index) in result.tool_trace" :key="`${item.tool}-${index}`">
            <span class="assistant-trace-index" aria-hidden="true">{{ index + 1 }}</span>
            <div class="assistant-trace-content">
              <strong>{{ toolLabel(item.tool) }}</strong>
              <span class="assistant-trace-status">{{ toolStatus(item.status) }}</span>
              <small>工具：{{ item.tool }}</small>
              <code>版本：{{ item.data_version }}</code>
            </div>
          </li>
        </ol>
      </section>

      <section class="assistant-report-section" aria-labelledby="assistant-sources-title">
        <div class="assistant-section-heading">
          <div>
            <p class="assistant-section-kicker">可复核数据</p>
            <h3 id="assistant-sources-title">来源指标</h3>
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
              <span class="assistant-source-status">已核验</span>
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

      <footer class="data-footer assistant-report-footer">
        <div class="assistant-boundary">
          <strong>统计边界</strong>
          <span>{{ result.boundary }}</span>
        </div>
        <div class="assistant-versions">
          <strong>报告数据版本</strong>
          <code v-for="version in result.data_versions" :key="version">{{ version }}</code>
        </div>
      </footer>
    </article>
  </div>
</template>
