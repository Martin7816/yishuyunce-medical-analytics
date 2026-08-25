<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()
const mainContent = ref(null)
const menuOpen = ref(false)
const menuButton = ref(null)
const sidebarClose = ref(null)
const screenShell = computed(() => route.path === '/overview')
const navigationGroups = [
  {
    label: '专题分析',
    items: [
      ['/hospitals', '医院运营', 'M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2M10 21v-4h4v4'],
      ['/diseases', '疾病分析', 'm4 4 6-2 10 4v14l-6 2-10-4V4Zm6-2v14m10-10-10 4m0 0L4 8'],
      ['/cohorts', '群体结构', 'M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm8-1a3 3 0 1 0 0-6m-12 11c0-3 2.7-5 6-5s6 2 6 5M16 13c2.5 0 4 1.4 4 4'],
      ['/costs', '费用分析', 'M12 3v18M16 7.5C16 6.1 14.2 5 12 5S8 6.1 8 7.5 9.8 10 12 10s4 1.1 4 2.5-1.8 2.5-4 2.5-4-1.1-4-2.5'],
      ['/risks', '严重程度', 'M12 3 21 7v5c0 5.1-3.4 8.3-9 9-5.6-.7-9-3.9-9-9V7l9-4Zm0 5v4m0 4h.01'],
      ['/payments', '支付方式', 'M3 6h18v12H3V6Zm0 4h18M7 15h4'],
    ],
  },
  {
    label: '智能能力',
    items: [
      ['/assistant', '运营洞察', 'M4 5h16v12H8l-4 4V5Zm4 5h.01M12 10h.01M16 10h.01'],
    ],
  },
]

function isActive(path) {
  return route.path === path || route.path.startsWith(`${path}/`)
}

function isGroupActive(group) {
  return group.items.some(item => isActive(item[0]))
}

function closeMenu(restoreFocus = false) {
  menuOpen.value = false
  if (restoreFocus) nextTick(() => menuButton.value?.focus())
}

async function toggleMenu() {
  menuOpen.value = !menuOpen.value
  await nextTick()
  if (menuOpen.value) sidebarClose.value?.focus()
  else menuButton.value?.focus()
}

async function focusPageTitle() {
  await nextTick()
  const target = document.querySelector('[data-page-title]') || mainContent.value
  target?.focus({ preventScroll: true })
}

watch(() => route.fullPath, () => {
  closeMenu()
  focusPageTitle()
})

onMounted(() => {
  if (window.matchMedia('(min-width: 721px)').matches) closeMenu()
})
</script>

<template>
  <div class="app-shell" :class="{ 'screen-shell': screenShell }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <header class="mobile-header">
      <RouterLink class="mobile-brand" to="/overview" aria-label="返回运营驾驶舱">
        <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 20 7v6c0 4.1-2.9 7.1-8 8-5.1-.9-8-3.9-8-8V7l8-4Zm0 5v7m-3.5-3.5h7" /></svg></span>
        <span><strong>医数云策</strong><small>医疗运营分析</small></span>
      </RouterLink>
      <button
        type="button"
        class="menu-button"
        ref="menuButton"
        aria-label="打开产品导航"
        :aria-expanded="menuOpen"
        aria-controls="product-navigation"
        @click="toggleMenu"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        <span>菜单</span>
      </button>
    </header>

    <div v-if="menuOpen" class="nav-scrim" aria-hidden="true" @click="closeMenu"></div>
    <aside id="product-navigation" class="sidebar" :class="{ 'is-open': menuOpen }" aria-label="产品导航" @keydown.esc="closeMenu(true)">
      <div class="sidebar-header">
        <RouterLink class="brand" to="/overview" aria-label="返回运营驾驶舱" @click="closeMenu">
          <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 20 7v6c0 4.1-2.9 7.1-8 8-5.1-.9-8-3.9-8-8V7l8-4Zm0 5v7m-3.5-3.5h7" /></svg></span>
          <span><strong>医数云策</strong><small>医疗运营分析平台</small></span>
        </RouterLink>
        <button ref="sidebarClose" type="button" class="sidebar-close" aria-label="关闭产品导航" @click="closeMenu(true)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>
      <RouterLink
        to="/overview"
        class="overview-entry"
        :aria-current="isActive('/overview') ? 'page' : undefined"
        @click="closeMenu"
      >
        <span class="overview-entry-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M4 5h16v11H4V5Zm5 15h6m-3-4v4" /></svg>
        </span>
        <span class="overview-entry-copy">
          <strong>运营总览</strong>
          <small>全局运营大屏</small>
        </span>
        <span class="overview-entry-arrow" aria-hidden="true">↗</span>
      </RouterLink>
      <nav aria-label="分析模块与工具">
        <section v-for="group in navigationGroups" :key="group.label" class="nav-group">
          <details v-if="group.collapsed" class="nav-disclosure" :open="isGroupActive(group)">
            <summary class="nav-section-title">{{ group.label }}</summary>
            <div class="nav-disclosure-items">
              <RouterLink
                v-for="item in group.items"
                :key="item[0]"
                :to="item[0]"
                :aria-current="isActive(item[0]) ? 'page' : undefined"
                @click="closeMenu"
              >
                <span class="nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path :d="item[2]" /></svg></span>
                <span>{{ item[1] }}</span>
              </RouterLink>
            </div>
          </details>
          <template v-else>
            <h2 class="nav-section-title">{{ group.label }}</h2>
            <RouterLink
              v-for="item in group.items"
              :key="item[0]"
              :to="item[0]"
              :aria-current="isActive(item[0]) ? 'page' : undefined"
              @click="closeMenu"
            >
              <span class="nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path :d="item[2]" /></svg></span>
              <span>{{ item[1] }}</span>
            </RouterLink>
          </template>
        </section>
      </nav>
      <p class="sidebar-note">住院出院记录 · 运营分析<br>面向医院管理与业务决策</p>
    </aside>

    <main id="main-content" ref="mainContent" class="main-content" tabindex="-1"><RouterView /></main>
  </div>
</template>
