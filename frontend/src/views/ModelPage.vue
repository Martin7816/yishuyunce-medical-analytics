<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { apiRequest, getApiErrorMessage } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import { displayOptionLabel } from '../domain/displayLabels.js'

const state = ref('loading')
const metrics = ref(null)
const error = ref(null)
const result = ref(null)
const predicting = ref(false)
const predictionError = ref(null)
const predictionState = ref('idle')
const predictionErrorPanel = ref(null)

const form = reactive({
  age_group: '50 to 69', gender: 'F', race: 'White', ethnicity: 'Not Span/Hispanic',
  hospital_service_area: 'New York City', facility_id: '1', admission_type: 'Emergency', emergency_indicator: 'Y',
})

const fields = [
  { key: 'age_group', label: '年龄组', options: ['0 to 17', '18 to 29', '30 to 49', '50 to 69', '70 or Older'] },
  { key: 'gender', label: '性别', options: ['F', 'M', 'U'] },
  { key: 'race', label: '种族', options: ['White', 'Black/African American', 'Other Race'] },
  { key: 'ethnicity', label: '族裔', options: ['Not Span/Hispanic', 'Spanish/Hispanic', 'Unknown'] },
  { key: 'hospital_service_area', label: '医院区域', options: ['New York City', 'Long Island', 'Hudson Valley', 'Other'] },
  { key: 'facility_id', label: '机构编号', options: ['1', '2', 'OTHER'] },
  { key: 'admission_type', label: '入院方式', options: ['Emergency', 'Urgent', 'Elective', 'Newborn', 'Trauma', 'Not Available'] },
  { key: 'emergency_indicator', label: '急诊标志', options: ['Y', 'N'] },
]

const confusionSection = computed(() => metrics.value?.sections?.find(section => section.key === 'confusion') || null)
const confusionItems = computed(() => {
  const values = Object.fromEntries((confusionSection.value?.items || []).map(item => [String(item.name).toUpperCase(), item.value]))
  return [
    { key: 'TN', label: '真阴性', value: values.TN },
    { key: 'FP', label: '假阳性', value: values.FP },
    { key: 'FN', label: '假阴性', value: values.FN },
    { key: 'TP', label: '真阳性', value: values.TP },
  ]
})
const supportingSections = computed(() => (metrics.value?.sections || []).filter(section => section.key !== 'confusion'))
const countFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0, useGrouping: false })

function formatCount(value) {
  return typeof value === 'number' ? countFormatter.format(value) : '—'
}

async function load() {
  state.value = 'loading'
  metrics.value = null
  error.value = null
  result.value = null
  predictionError.value = null
  predictionState.value = 'idle'
  try {
    const payload = await apiRequest('/models/high-cost/metrics')
    metrics.value = payload
    state.value = payload.metrics?.length || payload.sections?.length ? 'success' : 'empty'
  } catch (caught) {
    error.value = caught
    state.value = 'error'
  }
}

async function predict(values = form) {
  predicting.value = true
  predictionState.value = 'loading'
  result.value = null
  predictionError.value = null
  try {
    result.value = await apiRequest('/models/high-cost/predict', {
      method: 'POST',
      body: JSON.stringify({ ...values }),
    })
    predictionState.value = 'success'
  } catch (caught) {
    predictionError.value = caught
    predictionState.value = 'error'
    await nextTick()
    predictionErrorPanel.value?.focus()
  } finally {
    predicting.value = false
  }
}

function retryPrediction() {
  predict(form)
}

onMounted(load)
</script>

<template>
  <div class="page-wrap model-page" :aria-busy="state === 'loading' || predicting">
    <header class="page-heading">
      <div><p class="eyebrow">运营辅助分析</p><h1 id="page-title" data-page-title tabindex="-1">高费用记录识别</h1><p id="model-page-description">根据入院时可得的类别信息，辅助识别可能需要重点关注的高费用记录。</p></div>
    </header>
    <PageState v-if="state !== 'success'" :state="state" :error="error" @retry="load" />
    <template v-else>
      <p v-if="metrics.data_version?.startsWith('fixture:')" class="warning-note model-status-note">当前为演示数据，识别结果仅用于展示功能。</p>
      <section class="metric-grid"><MetricCard v-for="item in metrics.metrics" :key="item.key" :metric="item" /></section>
      <section class="model-grid">
        <article class="content-card evaluation-card">
          <h2 id="model-evaluation-title">识别表现</h2>
          <div v-if="confusionSection" class="confusion-block">
            <h3>{{ confusionSection.title }}</h3>
            <table class="confusion-table" aria-label="混淆矩阵">
              <colgroup><col class="matrix-label-column"><col><col></colgroup>
              <thead><tr>
                <th class="confusion-axis confusion-corner" scope="col">实际 / 预测</th>
                <th class="confusion-axis" scope="col">非高费用</th>
                <th class="confusion-axis" scope="col">高费用</th>
              </tr></thead>
              <tbody><tr>
                <th class="confusion-axis confusion-row-label" scope="row">非高费用</th>
                <td v-for="item in confusionItems.slice(0, 2)" :key="item.key" class="confusion-cell" :class="`confusion-${item.key.toLowerCase()}`">
                   <span>{{ item.label }}</span><strong>{{ formatCount(item.value) }}</strong>
                </td>
              </tr><tr>
                <th class="confusion-axis confusion-row-label" scope="row">高费用</th>
                <td v-for="item in confusionItems.slice(2)" :key="item.key" class="confusion-cell" :class="`confusion-${item.key.toLowerCase()}`">
                   <span>{{ item.label }}</span><strong>{{ formatCount(item.value) }}</strong>
                </td>
              </tr></tbody>
            </table>
            <p class="matrix-note">行表示真实标签，列表示模型预测；数值为测试集记录数。</p>
          </div>
          <p v-else class="section-empty">当前模型未发布混淆矩阵。</p>
          <AnalyticsChart v-for="section in supportingSections" :key="section.key" :section="section" />
        </article>
        <article class="content-card prediction-card"><h2 id="model-prediction-title">识别一条记录</h2><form class="prediction-form" aria-labelledby="model-prediction-title" :aria-busy="predicting" @submit.prevent="predict()">
          <label v-for="field in fields" :key="field.key" :for="`model-${field.key}`">{{ field.label }}
            <select :id="`model-${field.key}`" v-model="form[field.key]" required :aria-label="field.label" :disabled="predicting">
               <option v-for="option in field.options" :key="option" :value="option">{{ displayOptionLabel(field.key, option) }}</option>
            </select>
          </label>
          <button class="primary-button" :disabled="predicting">{{ predicting ? '正在计算' : '执行预测' }}</button>
        </form>
        <p v-if="predictionState === 'loading'" class="loading-note" role="status" aria-live="polite">正在提交预测请求，请稍候…</p>
        <div v-if="predictionError" ref="predictionErrorPanel" class="inline-error" role="alert" tabindex="-1" aria-labelledby="prediction-error-title"><strong id="prediction-error-title">{{ getApiErrorMessage(predictionError) }}</strong><button type="button" class="secondary-button" @click="retryPrediction">重试识别</button></div>
        <div v-if="result" class="prediction-result" role="status" aria-live="polite" aria-label="识别结果"><strong>{{ result.prediction === 'HIGH_COST' ? '高费用记录' : '非高费用记录' }}</strong><span>识别概率 {{ (result.probability * 100).toFixed(1) }}%</span><small>结果仅作为运营分析参考，不用于个人医疗判断。</small></div>
        </article>
      </section>
      <footer class="data-footer"><span>高费用记录识别仅用于运营分析</span><span>不提供个人诊断或治疗建议</span></footer>
    </template>
  </div>
</template>
