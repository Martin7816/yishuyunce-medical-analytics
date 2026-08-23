<script setup>
defineProps({ insights: { type: Array, default: () => [] }, stage: Boolean })
</script>

<template>
  <section v-if="stage || insights.length" class="insight-panel content-card" aria-labelledby="insight-heading">
    <div class="insight-heading">
      <div><p class="eyebrow">运营提示</p><h2 id="insight-heading">关键发现</h2></div>
      <span class="insight-badge">基于汇总数据</span>
    </div>
    <p v-if="!insights.length" class="section-empty insight-empty">当前暂无可确认的运营提示，请结合上方指标和图表查看。</p>
    <div v-for="insight in insights" :key="insight.key" class="insight-item">
      <div><h3>{{ insight.title }}</h3><p>{{ insight.summary }}</p></div>
    </div>
    <p v-if="insights.length" class="insight-boundary">提示仅用于观察住院出院记录的群体结构，相关不等于因果。</p>
  </section>
</template>
