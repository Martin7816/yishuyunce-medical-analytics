<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiRequest, isAbortError } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import {
  dashboardSectionQuestion,
  dashboardSections,
  drilldownTarget,
  screenInsights as getScreenInsights,
  screenMetricSelection,
  screenSections as getScreenSections,
} from '../domain/dashboard.js'

const route = useRoute()
const router = useRouter()
const state = ref('loading')
const payload = ref(null)
const error = ref(null)
let activeController = null
let requestId = 0

const isScreen = computed(() => route.query.mode === 'screen')
const screenData = computed(() => dashboardSections(payload.value || {}))
const metrics = computed(() => payload.value?.metrics || [])
const isFixture = computed(() => payload.value?.data_version?.startsWith('fixture:'))
const correlations = computed(() => screenData.value.correlations?.items || [])
const screenMetricList = computed(() => screenMetricSelection(metrics.value))
const screenView = computed(() => getScreenSections(payload.value || {}))
const screenInsightList = computed(() => getScreenInsights(payload.value || {}))

const panelClass = {
  age: 'panel-age',
  payment: 'panel-payment',
  disease_top10: 'panel-disease',
  hospital_top10: 'panel-hospital',
  cost_los_relation: 'panel-cost',
  age_severity_matrix: 'panel-risk',
}

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

function switchMode() {
  const query = { ...route.query }
  if (isScreen.value) delete query.mode
  else query.mode = 'screen'
  router.push({ path: '/overview', query })
}

watch(() => route.query.mode, load)
onMounted(load)
onBeforeUnmount(() => {
  activeController?.abort()
})
</script>

<template>
  <div class="overview-page" :class="{ 'is-screen': isScreen }">
    <header class="overview-header">
      <div class="overview-title-block">
        <p class="overview-eyebrow">医数云策 · 医院运营全景</p>
        <h1 data-page-title tabindex="-1">{{ isScreen ? '运营全景展示' : '运营分析工作台' }}</h1>
        <p v-if="!isScreen" class="overview-description">从住院出院记录规模、医院、疾病、费用与风险结构理解运营现状。</p>
      </div>
      <div class="overview-actions">
        <button type="button" class="secondary-button" @click="load">刷新数据</button>
        <button type="button" class="secondary-button" @click="switchMode">{{ isScreen ? '返回工作台' : '进入展示模式' }}</button>
      </div>
    </header>

    <p v-if="isScreen" class="display-note" role="note">运营观察台展示模式：聚焦本批次的结构、集中度与关系摘要；建议浏览器缩放保持 100%。</p>
    <p v-if="isFixture" class="fixture-warning" role="note"><strong>演示数据</strong> 当前指标用于展示分析功能，不作为实际运营结论。</p>

    <div v-if="state === 'loading'" class="overview-loading" aria-busy="true" aria-live="polite">
      <span class="sr-only">正在加载运营大屏</span>
      <div v-for="index in 8" :key="`metric-${index}`" class="skeleton-block skeleton-metric"></div>
      <div v-for="index in 6" :key="`panel-${index}`" class="skeleton-block skeleton-panel"></div>
    </div>
    <PageState v-else-if="state !== 'success'" :state="state" :error="error" @retry="load" />

    <template v-else>
      <template v-if="isScreen">
        <section class="screen-insight-rail" aria-label="本批次运营摘要">
          <div class="screen-rail-heading">
            <span class="screen-kicker">EXECUTIVE READOUT</span>
            <strong>本批次运营摘要</strong>
            <small>只读快照 · 先看结构，再进入专题</small>
          </div>
          <div v-if="screenInsightList.length" class="screen-insight-list">
            <article v-for="insight in screenInsightList.slice(0, 3)" :key="insight.key" class="screen-insight-item">
              <strong>{{ insight.title }}</strong>
              <p>{{ insight.summary }}</p>
              <small>{{ insight.related_not_causal ? '关系描述，不作因果判断' : '来源：已发布分析快照' }}</small>
            </article>
          </div>
          <p v-else class="screen-insight-empty">当前批次没有可展示的摘要，请进入专题页查看数据状态。</p>
        </section>

        <section class="overview-metrics screen-metrics" aria-label="展示模式核心指标">
          <MetricCard v-for="metric in screenMetricList" :key="metric.key" :metric="metric" />
        </section>

        <section class="screen-visual-grid" aria-label="运营全景结构扫描">
          <article class="screen-card screen-structure-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">STRUCTURE</span><h2>人群与支付结构</h2></div>
              <span class="screen-card-index">01</span>
            </header>
            <div class="screen-dual-chart">
              <div v-if="screenView.age">
                <h3>{{ screenView.age.title }}</h3>
                <AnalyticsChart :section="screenView.age" compact :show-question="false" business-mode @select="item => selectPanel(screenView.age, item)" />
              </div>
              <div v-if="screenView.payment">
                <h3>{{ screenView.payment.title }}</h3>
                <AnalyticsChart :section="screenView.payment" compact :show-question="false" business-mode @select="item => selectPanel(screenView.payment, item)" />
              </div>
            </div>
          </article>

          <article v-if="screenView.disease" class="screen-card screen-ranking-card screen-disease-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">DISEASE MIX</span><h2>疾病病例量集中度</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.disease, {})">查看专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.disease" compact :show-question="false" business-mode @select="item => selectPanel(screenView.disease, item)" />
          </article>

          <article v-if="screenView.hospital" class="screen-card screen-ranking-card screen-hospital-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">FACILITY MIX</span><h2>机构病例量分布</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.hospital, {})">查看专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.hospital" compact :show-question="false" business-mode @select="item => selectPanel(screenView.hospital, item)" />
          </article>

          <article v-if="screenView.relation" class="screen-card screen-relation-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">COST RELATION</span><h2>费用与住院时长关系</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.relation, {})">查看专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.relation" compact :show-question="false" business-mode @select="item => selectPanel(screenView.relation, item)" />
            <div class="correlation-strip" aria-label="费用相关性证据">
              <div v-for="item in correlations" :key="`${item.x_key}-${item.y_key}`">
                <span>{{ item.x_label }} × {{ item.y_label }}</span>
                <strong>r = {{ Number(item.coefficient).toFixed(4) }}</strong>
                <small>n = {{ Number(item.sample_size).toLocaleString('zh-CN') }}</small>
              </div>
              <p>Pearson · 相关不等于因果</p>
            </div>
          </article>

          <article v-if="screenView.risk" class="screen-card screen-risk-card">
            <header class="screen-card-header">
              <div><span class="screen-card-code">RISK STRUCTURE</span><h2>年龄与严重程度结构</h2></div>
              <button type="button" class="card-link screen-card-link" @click="selectPanel(screenView.risk, {})">查看专题 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="screenView.risk" compact :show-question="false" business-mode @select="item => selectPanel(screenView.risk, item)" />
          </article>
        </section>
      </template>

      <template v-else>
        <section class="overview-metrics" aria-label="核心运营指标">
          <MetricCard v-for="metric in metrics" :key="metric.key" :metric="metric" />
        </section>

        <section class="dashboard-grid" aria-label="运营分析图表">
          <article
            v-for="section in screenData.panels"
            :key="section.key"
            class="dashboard-card"
            :class="panelClass[section.key]"
          >
            <header class="dashboard-card-header">
              <div><p>{{ dashboardSectionQuestion(section) }}</p><h2>{{ section.title }}</h2></div>
              <button type="button" class="card-link" @click="selectPanel(section, {})">专题分析 <span aria-hidden="true">→</span></button>
            </header>
            <AnalyticsChart :section="section" :compact="false" :show-question="false" business-mode @select="item => selectPanel(section, item)" />
            <div v-if="section.key === 'cost_los_relation'" class="correlation-strip" aria-label="费用相关性证据">
              <div v-for="item in correlations" :key="`${item.x_key}-${item.y_key}`">
                <span>{{ item.x_label }} × {{ item.y_label }}</span>
                <strong>r = {{ Number(item.coefficient).toFixed(4) }}</strong>
                <small>n = {{ Number(item.sample_size).toLocaleString('zh-CN') }}</small>
              </div>
              <p>Pearson · 相关不等于因果</p>
            </div>
          </article>
        </section>
      </template>

      <footer class="overview-footnote">
        <span>统计对象为住院出院记录；页面不关联同一人的多次住院。</span>
        <span>{{ isScreen ? '点击图表标记或“查看专题”进入详细分析。' : '点击图表或“专题分析”查看对应的详细分析。' }}</span>
      </footer>
    </template>
  </div>
</template>
