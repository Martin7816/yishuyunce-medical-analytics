<script setup>
import { getApiErrorMessage } from '../api/client.js'

defineProps({ state: String, error: Object, message: { type: String, default: '' } })
defineEmits(['retry', 'clear'])
</script>
<template>
  <section class="state-panel" :class="state" :role="state === 'error' || state === 'validation' ? 'alert' : 'status'" :aria-live="state === 'error' || state === 'validation' ? 'assertive' : 'polite'" :aria-busy="state === 'loading'">
    <span class="state-symbol" aria-hidden="true">
      <svg v-if="state === 'loading'" viewBox="0 0 24 24" class="state-spinner"><path d="M12 3a9 9 0 1 0 9 9" /></svg>
      <svg v-else-if="state === 'empty'" viewBox="0 0 24 24"><path d="M5 12h14" /></svg>
      <svg v-else-if="state === 'validation'" viewBox="0 0 24 24"><path d="M12 3 21 20H3L12 3Zm0 6v5m0 3h.01" /></svg>
      <svg v-else viewBox="0 0 24 24"><path d="M12 3 21 20H3L12 3Zm0 6v5m0 3h.01" /></svg>
    </span>
    <h2>{{ state === 'loading' ? '正在加载分析数据' : state === 'empty' ? '当前条件暂无数据' : state === 'validation' ? '请先修正筛选条件' : '数据加载失败' }}</h2>
    <p v-if="state === 'error'">{{ getApiErrorMessage(error) }}</p>
    <p v-else-if="state === 'validation'">{{ message || '当前链接中的筛选参数不受支持。' }}</p>
    <p v-else-if="state === 'empty'">当前筛选条件没有可展示的住院出院记录。</p>
    <button v-if="state === 'error'" type="button" class="primary-button" @click="$emit('retry')">重新加载</button>
    <button v-if="state === 'validation'" type="button" class="primary-button" @click="$emit('clear')">清除无效参数</button>
    <button v-if="state === 'empty'" type="button" class="secondary-button" @click="$emit('retry')">重新读取</button>
  </section>
</template>
