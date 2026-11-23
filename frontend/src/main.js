// 文件基本信息：frontend/src/main.js
// 目的：创建 Vue 应用并挂载 App.vue。
// 输入：浏览器 DOM 和 Vue 应用模块。
// 输出：挂载到 #app 的前端应用。
// 维护：修改入口时同步 frontend/src/目录索引.md 和 UI 验收场景。

import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
