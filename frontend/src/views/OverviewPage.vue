<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { apiRequest, isAbortError } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import {
  dashboardSections,
  drilldownTarget,
  screenMetricSelection,
  screenSections as getScreenSections,
} from '../domain/dashboard.js'
import { displayFieldLabel, displayText } from '../domain/displayLabels.js'

const router = useRouter()
const state = ref('loading')
const payload = ref(null)
const error = ref(null)
let activeController = null
let requestId = 0

const screenData = computed(() => dashboardSections(payload.value || {}))
const metrics = computed(() => payload.value?.metrics || [])
const isFixture = computed(() => payload.value?.data_version?.startsWith('fixture:'))
const correlations = computed(() => screenData.value.correlations?.items || [])
const sharedCorrelationSample = computed(() => {
  const samples = correlations.value.map(item => Number(item.sample_size)).filter(Number.isFinite)
  return samples.length && new Set(samples).size === 1 ? samples[0] : null
})
const screenMetricList = computed(() => screenMetricSelection(metrics.value))
const screenView = computed(() => getScreenSections(payload.value || {}))
const topicLinks = Object.freeze([
  { path: '/hospitals', label: '医院运营' },
  { path: '/diseases', label: '疾病分析' },
  { path: '/cohorts', label: '群体结构' },
  { path: '/costs', label: '费用分析' },
  { path: '/risks', label: '严重程度' },
  { path: '/payments', label: '支付方式' },
])

function hasContent(data) {
  return Boolean(data?.metrics?.length && dashboardSections(data).panels.some(section => section.items?.length))
}

async function load() {
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  const currentRequest = ++requestId
  state.value = 'loading'
  error.value = null
  try {
    const data = await apiRequest('/dashboard/screen', { signal: controller.signal })
    if (currentRequest !== requestId) return
    payload.value = data
    state.value = hasContent(data) ? 'success' : 'empty'
  } catch (cause) {
    if (isAbortError(cause) || currentRequest !== requestId) return
    error.value = cause
    state.value = 'error'
  }
}

function selectPanel(section, item) {
  router.push(drilldownTarget(section.key, item, payload.value?.options || {}))
}

onMounted(load)
onBeforeUnmount(() => {
  activeController?.abort()
})
</script>

<template>
  <div class="overview-page is-screen">
    <header class="overview-header">
      <div class="overview-title-block">
        <p class="overview-eyebrow">医数云策 · 医院运营全景</p>
        <h1 data-page-title tabindex="-1">运营总览</h1>
      </div>
      <div class="overview-actions">
        <RouterLink to="/assistant" class="overview-insight-link" aria-label="进入运营洞察">
          <span class="overview-insight-badge" aria-hidden="true">AI</span>
          <span>运营洞察</span><span aria-hidden="true">→</span>
        </RouterLink>
        <button type="button" class="secondary-button" @click="load">刷新数据</button>
      </div>
    </header>

    <nav class="overview-topic-nav" aria-label="专题分析导航">
      <span class="overview-topic-nav-label">专题分析</span>
      <div class="overview-topic-links">
        <RouterLink v-for="topic in topicLinks" :key="topic.path" :to="topic.path" class="overview-topic-link">
          <span>{{ topic.label }}</span><span aria-hidden="true">→</span>
        </RouterLink>
      </div>
    </nav>

    <p v-if="isFixture" class="fixture-warning" role="note"><strong>演示数据</strong> 当前指标用于展示分析功能，不作为实际运营结论。</p>

    <div v-if="state === 'loading'" class="overview-loading" aria-busy="true" aria-live="polite">
      <span class="sr-only">正在加载运营大屏</span>
      <div v-for="index in 8" :key="`metric-${index}`" class="skeleton-block skeleton-metric"></div>
      <div v-for="index in 6" :key="`panel-${index}`" class="skeleton-block skeleton-panel"></div>
    </div>
    <PageState v-else-if="state !== 'success'" :state="state" :error="error" @retry="load" />

    <template v-else>
        <section class="overview-metrics screen-metrics" aria-label="核心运营指标">
          <MetricCard v-for="metric in screenMetricList" :key="metric.key" :metric="metric" plain-number />
        </section>

        <section class="screen-visual-grid" aria-label="运营总览分析">
          <article class="screen-card screen-structure-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">结构分析</span><h2>人群与支付结构</h2></div>
            </header>
            <div class="screen-dual-chart">
              <div v-if="screenView.age">
                <h3>{{ displayText(screenView.age.title) }}</h3>
                <AnalyticsChart :section="screenView.age" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.age, item)" />
              </div>
              <div v-if="screenView.payment">
                <h3>{{ displayText(screenView.payment.title) }}</h3>
                <AnalyticsChart :section="screenView.payment" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.payment, item)" />
              </div>
            </div>
          </article>

          <article v-if="screenView.disease" class="screen-card screen-ranking-card screen-disease-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">疾病排行</span><h2>主要疾病病例量排行</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.disease, {})">进入专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.disease" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.disease, item)" />
          </article>

          <article v-if="screenView.hospital" class="screen-card screen-ranking-card screen-hospital-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">机构排行</span><h2>主要机构病例量 Top 10</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.hospital, {})">进入专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.hospital" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.hospital, item)" />
          </article>

          <article v-if="screenView.relation" class="screen-card screen-relation-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">费用关系</span><h2>{{ screenView.relation.key === 'cost_los_overview' ? '收费与住院时长总览' : '收费与住院时长关系' }}</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.relation, {})">进入专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.relation" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.relation, item)" />
            <div class="correlation-strip" aria-label="费用相关性证据">
              <div class="correlation-strip-heading">
                <span>相关性摘要</span>
                <small v-if="sharedCorrelationSample">成对有效记录 n = {{ Number(sharedCorrelationSample).toLocaleString('zh-CN', { useGrouping: false }) }}</small>
              </div>
              <div class="correlation-strip-items">
                <div v-for="item in correlations" :key="`${item.x_key}-${item.y_key}`" class="correlation-item">
                  <span>{{ displayText(displayFieldLabel(item.x_label)) }} × {{ displayText(displayFieldLabel(item.y_label)) }}</span>
                  <strong>r = {{ Number(item.coefficient).toFixed(4) }}</strong>
                  <small v-if="!sharedCorrelationSample">n = {{ Number(item.sample_size).toLocaleString('zh-CN', { useGrouping: false }) }}</small>
                </div>
              </div>
              <p>皮尔逊 · 相关不等于因果</p>
            </div>
          </article>

          <article v-if="screenView.risk" class="screen-card screen-risk-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">风险结构</span><h2>年龄与重症程度结构</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.risk, {})">进入专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.risk" compact :show-question="false" business-mode screen-mode @select="item => selectPanel(screenView.risk, item)" />
           </article>

        </section>
      <footer class="overview-footnote">
        <span>统计对象为住院出院记录；页面不关联同一人的多次住院。</span>
        <span>点击图表标记或“进入专题”查看详细分析。</span>
      </footer>
    </template>
  </div>
</template>
