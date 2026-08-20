<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiRequest, getApiErrorMessage } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const state = ref('loading')
const metrics = ref(null)
const error = ref(null)
const result = ref(null)
const predicting = ref(false)
const predictionError = ref(null)

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

async function load() {
  state.value = 'loading'
  metrics.value = null
  error.value = null
  result.value = null
  predictionError.value = null
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
  result.value = null
  predictionError.value = null
  try {
    result.value = await apiRequest('/models/high-cost/predict', {
      method: 'POST',
      body: JSON.stringify({ ...values }),
    })
  } catch (caught) {
    predictionError.value = caught
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
  <div class="page-wrap">
    <header class="page-heading">
      <div><p class="eyebrow">可复现的运营分类</p><h1>高费用病例分类模型</h1><p>阈值仅由训练集收费 P75 产生；预测只使用入院时可得类别字段。</p></div>
      <span v-if="metrics" class="version-pill" :title="metrics.model_version">{{ metrics.model_version }}</span>
    </header>
    <PageState v-if="state !== 'success'" :state="state" :error="error" @retry="load" />
    <template v-else>
      <p v-if="metrics.data_version?.startsWith('fixture:')" class="warning-note">当前指标来自固定联调工件，不代表真实模型效果；正式演示必须替换为 PySpark 训练工件。</p>
      <p class="warning-note">用于群体运营分析，不构成诊断或治疗建议。收费、成本、住院时长和出院后字段均未进入特征。</p>
      <section class="metric-grid"><MetricCard v-for="item in metrics.metrics" :key="item.key" :metric="item" /></section>
      <section class="model-grid">
        <article class="content-card"><h2>评估结果</h2><AnalyticsChart v-for="section in metrics.sections" :key="section.key" :section="section" /></article>
        <article class="content-card"><h2>单条记录预测</h2><form class="prediction-form" @submit.prevent="predict()">
          <label v-for="field in fields" :key="field.key" :for="`model-${field.key}`">{{ field.label }}
            <select :id="`model-${field.key}`" v-model="form[field.key]" required :aria-label="field.label">
              <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <button class="primary-button" :disabled="predicting">{{ predicting ? '正在计算' : '执行预测' }}</button>
        </form>
        <div v-if="predictionError" class="inline-error" role="alert"><strong>{{ getApiErrorMessage(predictionError) }}</strong><small v-if="predictionError.traceId">追踪编号：{{ predictionError.traceId }}</small><button type="button" class="secondary-button" @click="retryPrediction">重试预测</button></div>
        <div v-if="result" class="prediction-result"><strong>{{ result.prediction === 'HIGH_COST' ? '高费用记录' : '非高费用记录' }}</strong><span>概率 {{ (result.probability * 100).toFixed(1) }}%</span><span v-if="result.threshold_amount != null">高费用阈值：{{ Number(result.threshold_amount).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} 美元</span><small>{{ result.model_version }} · {{ result.data_version }}<br><b v-if="result.fixture_only">当前为固定联调工件，不代表真实模型评估。</b><br>{{ result.boundary }}</small></div>
        </article>
      </section>
    </template>
  </div>
</template>
