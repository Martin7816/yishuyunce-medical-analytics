<script setup>
defineProps({ state: String, error: Object })
defineEmits(['retry'])
const messages = {
  DATABASE_UNAVAILABLE: '数据服务暂时不可用。', RESULT_NOT_READY: '该分析结果尚未发布。',
  SERVER_MISCONFIGURED: '服务配置不完整。', UPSTREAM_SERVICE_ERROR: 'AI 服务暂时不可用。',
  NETWORK_ERROR: '无法连接后端服务。', HTTP_ERROR: '数据服务返回了暂时无法处理的响应。',
  INVALID_QUERY_PARAMETER: '筛选值不受支持。', INVALID_REQUEST_FIELD: '请求字段不受支持。',
  INVALID_REQUEST_FORMAT: '请求格式不受支持。', SERVICE_RESULT_INVALID: '分析结果格式无法验证。',
}
function messageFor(error) { return messages[error?.code] || '数据加载失败，请稍后重试。' }
</script>
<template>
  <section class="state-panel" :class="state" :role="state === 'error' ? 'alert' : 'status'" :aria-live="state === 'error' ? 'assertive' : 'polite'" :aria-busy="state === 'loading'">
    <span class="state-symbol">{{ state === 'loading' ? '···' : state === 'empty' ? '—' : '!' }}</span>
    <h2>{{ state === 'loading' ? '正在加载分析快照' : state === 'empty' ? '当前条件暂无数据' : '数据加载失败' }}</h2>
    <p v-if="state === 'error'">{{ messageFor(error) }}</p>
    <small v-if="error?.code">错误类型：{{ error.code }}</small>
    <small v-if="error?.traceId">追踪编号：{{ error.traceId }}</small>
    <button v-if="state === 'error'" class="primary-button" @click="$emit('retry')">重新加载</button>
  </section>
</template>
