<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiRequest } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const state = ref('loading'), metrics = ref(null), error = ref(null), result = ref(null), predicting = ref(false)
const form = reactive({
  age_group: '50 to 69', gender: 'F', race: 'White', ethnicity: 'Not Span/Hispanic',
  hospital_service_area: 'New York City', facility_id: '1', admission_type: 'Emergency', emergency_indicator: 'Y',
})
const fields = [
  ['age_group', '年龄组'], ['gender', '性别'], ['race', '种族'], ['ethnicity', '族裔'],
  ['hospital_service_area', '医院区域'], ['facility_id', '机构编号'], ['admission_type', '入院方式'], ['emergency_indicator', '急诊标志'],
]
async function load() {
  state.value = 'loading'
  try { metrics.value = await apiRequest('/models/high-cost/metrics'); state.value = 'success' }
  catch (caught) { error.value = caught; state.value = 'error' }
}
async function predict() {
  predicting.value = true; result.value = null; error.value = null
  try { result.value = await apiRequest('/models/high-cost/predict', { method: 'POST', body: JSON.stringify(form) }) }
  catch (caught) { error.value = caught }
  finally { predicting.value = false }
}
onMounted(load)
</script>
<template>
  <div class="page-wrap">
    <header class="page-heading"><div><p class="eyebrow">可复现的运营分类</p><h1>高费用病例分类模型</h1><p>阈值仅由训练集收费 P75 产生；预测只使用入院时可得类别字段。</p></div><span v-if="metrics" class="version-pill">{{ metrics.model_version }}</span></header>
    <PageState v-if="state !== 'success'" :state="state" :error="error" @retry="load" />
    <template v-else>
      <p v-if="metrics.data_version?.startsWith('fixture:')" class="warning-note">当前指标来自固定联调工件，不代表真实模型效果；正式演示必须替换为 PySpark 训练工件。</p>
      <p class="warning-note">用于群体运营分析，不构成诊断或治疗建议。收费、成本、住院时长和出院后字段均未进入特征。</p>
      <section class="metric-grid"><MetricCard v-for="item in metrics.metrics" :key="item.key" :metric="item" /></section>
      <section class="model-grid">
        <article class="content-card"><h2>评估结果</h2><AnalyticsChart v-for="section in metrics.sections" :key="section.key" :section="section" /></article>
        <article class="content-card"><h2>单条记录预测</h2><form class="prediction-form" @submit.prevent="predict">
          <label v-for="field in fields" :key="field[0]">{{ field[1] }}<input v-model.trim="form[field[0]]" required /></label>
          <button class="primary-button" :disabled="predicting">{{ predicting ? '正在计算' : '执行预测' }}</button>
        </form>
        <div v-if="result" class="prediction-result"><strong>{{ result.prediction === 'HIGH_COST' ? '高费用记录' : '非高费用记录' }}</strong><span>概率 {{ (result.probability * 100).toFixed(1) }}%</span><small>{{ result.model_version }} · {{ result.data_version }}<br><b v-if="result.fixture_only">当前为固定联调工件，不代表真实模型评估。</b></small></div>
        <p v-if="error" class="inline-error">{{ error.message }}</p></article>
      </section>
    </template>
  </div>
</template>
