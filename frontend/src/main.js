import { createApp } from 'vue'
import './styles/tokens.css'
import './style.css'
import './styles/dashboard.css'
import App from './App.vue'
import router from './router.js'

createApp(App).use(router).mount('#app')
