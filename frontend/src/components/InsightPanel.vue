<script setup>
defineProps({ insights: { type: Array, default: () => [] }, stage: Boolean })
</script>

<template>
  <section v-if="stage || insights.length" class="insight-panel content-card" aria-labelledby="insight-heading">
    <div class="insight-heading">
      <div><p class="eyebrow">后端确定性摘要</p><h2 id="insight-heading">分析叙事与边界</h2></div>
      <span class="insight-badge">不把相关当因果</span>
    </div>
    <p v-if="!insights.length" class="section-empty insight-empty">当前快照未发布确定性洞察；请以图表和数据表为事实来源。</p>
    <div v-for="insight in insights" :key="insight.key" class="insight-item">
      <div><h3>{{ insight.title }}</h3><p>{{ insight.summary }}</p></div>
      <dl class="insight-meta">
        <div><dt>来源 section</dt><dd>{{ insight.source_section }}</dd></div>
        <div><dt>来源指标</dt><dd>{{ insight.source_metric_keys.join('、') }}</dd></div>
        <div><dt>统计边界</dt><dd>{{ insight.boundary }}</dd></div>
        <div><dt>数据版本</dt><dd>{{ insight.data_version }}</dd></div>
      </dl>
    </div>
  </section>
</template>
