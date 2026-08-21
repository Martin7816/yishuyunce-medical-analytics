<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()
const screenShell = computed(() => route.path === '/overview' && route.query.mode === 'screen')
const navigation = [
  ['/overview', '运营驾驶舱', '总'], ['/hospitals', '医院运营分析', '院'], ['/diseases', '疾病画像分析', '病'], ['/cohorts', '住院群体分析', '群'],
  ['/costs', '费用成本分析', '费'], ['/risks', '病情风险分析', '险'], ['/payments', '支付方式分析', '付'], ['/data-quality', '数据质量管理', '质'],
  ['/model', '高费用记录分类', '模'], ['/assistant', 'AI 问答与报告', 'AI'],
]
</script>

<template>
  <div class="app-shell" :class="{ 'screen-shell': screenShell }">
    <aside class="sidebar">
      <a class="skip-link" href="#analysis-content">跳到主要内容</a>
      <div class="brand"><span class="brand-mark">医</span><div><strong>医数云策</strong><small>医疗运营分析平台</small></div></div>
      <nav aria-label="产品模块"><RouterLink v-for="item in navigation" :key="item[0]" :to="item[0]"><span class="nav-icon">{{ item[2] }}</span><span>{{ item[1] }}</span></RouterLink></nav>
      <p class="sidebar-note">群体统计 · 非个人诊断<br>SPARCS 住院出院记录</p>
    </aside>
    <main class="main-content"><RouterView /></main>
  </div>
</template>
