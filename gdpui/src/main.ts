import Vue from 'vue'
import App from './App.vue'
import router from './router'
import pinia from './stores'

// Element UI (Vue 2 version)
import ElementUI from 'element-ui'
import 'element-ui/lib/theme-chalk/index.css'

// FontAwesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'

// Global styles (Tailwind v4 entry + project styles)
import './assets/styles/main.css'

library.add(fas)
Vue.component('font-awesome-icon', FontAwesomeIcon)

Vue.use(ElementUI)

Vue.config.productionTip = false

// 全局错误边界：捕获组件渲染/生命周期中的未处理异常
Vue.config.errorHandler = (err: Error, vm: Vue, info: string) => {
  console.error('[Vue Error]', info, err)
  // 使用 Element UI Message 组件提示用户
  Vue.prototype.$message?.error?.(`应用出错: ${err.message || '未知错误'}`)
}

// 捕获 Promise 未处理的 rejection
window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  console.error('[Unhandled Rejection]', event.reason)
})

new Vue({
  router,
  pinia,
  render: (h) => h(App),
}).$mount('#app')
