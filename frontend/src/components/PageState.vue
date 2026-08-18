<script setup>
import { getApiErrorMessage } from '../api/client.js'

defineProps({ state: String, error: Object })
defineEmits(['retry'])
</script>
<template>
  <section class="state-panel" :class="state" :role="state === 'error' ? 'alert' : 'status'" :aria-live="state === 'error' ? 'assertive' : 'polite'" :aria-busy="state === 'loading'">
    <span class="state-symbol">{{ state === 'loading' ? '···' : state === 'empty' ? '—' : '!' }}</span>
    <h2>{{ state === 'loading' ? '正在加载分析快照' : state === 'empty' ? '当前条件暂无数据' : '数据加载失败' }}</h2>
    <p v-if="state === 'error'">{{ getApiErrorMessage(error) }}</p>
    <small v-if="error?.code">错误类型：{{ error.code }}</small>
    <small v-if="error?.traceId">追踪编号：{{ error.traceId }}</small>
    <button v-if="state === 'error'" type="button" class="primary-button" @click="$emit('retry')">重新加载</button>
  </section>
</template>
