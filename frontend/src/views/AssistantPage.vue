<script setup>
import { ref } from 'vue'
import { apiRequest, getApiErrorMessage } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'

const question = ref('请概括当前运营情况，并说明引用的数据版本。')
const result = ref(null)
const error = ref(null)
const loading = ref(false)
const lastQuestion = ref('')
const presets = ['概括当前运营情况', '费用与成本有哪些主要特征？', '疾病病例量排名如何？', '高费用模型表现如何？']

function hasUsableSources(payload) {
  return Array.isArray(payload?.sources)
    && payload.sources.length > 0
    && Array.isArray(payload?.data_versions)
    && payload.data_versions.length > 0
}

async function ask(value = question.value) {
  const text = value.trim()
  if (!text) return
  lastQuestion.value = text
  question.value = text
  loading.value = true
  result.value = null
  error.value = null
  try {
    const payload = await apiRequest('/ai/chat', { method: 'POST', body: JSON.stringify({ message: text }) })
    if (!hasUsableSources(payload)) throw Object.assign(new Error('AI 返回缺少可核验来源。'), { code: 'SERVICE_RESULT_INVALID' })
    result.value = payload
  } catch (caught) {
    error.value = caught
  } finally {
    loading.value = false
  }
}

function choose(value) { ask(value) }
function retry() { ask(lastQuestion.value || question.value) }
function formatSourceMetrics(source) {
  return (source?.metrics || []).map(item => `${item.label}: ${item.value}${item.unit || ''}`).join('；')
}
function printReport() { window.print() }
</script>

<template>
  <div class="page-wrap assistant-page">
    <header class="page-heading"><div><p class="eyebrow">DeepSeek · 白名单分析工具</p><h1>AI 大模型问答与洞察报告</h1><p>模型只能读取已发布汇总快照，不执行 SQL，也不保存多轮历史。</p></div></header>
    <section class="ask-card" :aria-busy="loading">
      <div class="preset-row"><button v-for="preset in presets" :key="preset" type="button" @click="choose(preset)">{{ preset }}</button></div>
      <form @submit.prevent="ask()"><textarea v-model="question" maxlength="1000" rows="4" aria-label="分析问题" required></textarea><button class="primary-button" :disabled="loading">{{ loading ? '正在调用分析工具…' : '提交问题' }}</button></form>
      <p v-if="loading" class="loading-note" aria-live="polite">正在调用白名单分析工具，请稍候。</p>
    </section>
    <section v-if="error" class="state-panel error" role="alert"><span class="state-symbol">!</span><h2>AI 服务未能完成回答</h2><p>{{ getApiErrorMessage(error) }}</p><small v-if="error.code">错误类型：{{ error.code }}</small><small v-if="error.traceId">追踪编号：{{ error.traceId }}</small><button type="button" class="primary-button" @click="retry">重新加载</button></section>
    <article v-if="result" class="answer-sheet">
      <div class="answer-heading"><div><p class="eyebrow">医数云策洞察简报</p><h2>分析回答</h2></div><button type="button" @click="printReport">打印 / 导出 PDF</button></div>
      <p class="answer-text">{{ result.answer }}</p>
      <AnalyticsChart v-if="result.chart" :section="result.chart" />
      <section><h3>工具执行过程</h3><ol class="tool-trace"><li v-for="item in result.tool_trace" :key="item.tool"><strong>{{ item.tool }}</strong><span>{{ item.status }}</span><small>{{ item.data_version }}</small></li></ol></section>
      <section><h3>来源指标</h3><div v-for="source in result.sources" :key="source.tool" class="source-block"><strong>{{ source.title }}</strong><p>{{ formatSourceMetrics(source) }}</p><small>{{ source.data_version }}</small></div></section>
      <footer class="data-footer"><span v-for="version in result.data_versions" :key="version">数据版本：{{ version }}</span><span>{{ result.boundary }}</span></footer>
    </article>
  </div>
</template>
