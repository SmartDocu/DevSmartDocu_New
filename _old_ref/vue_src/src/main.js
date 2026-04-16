import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import master_chapter_template_vue from './components/master_chapter_template.vue'

// createApp(App).mount('#app')
const master_chapter_template = createApp(master_chapter_template_vue, window.__INITIAL_DATA__)
master_chapter_template.mount('#master_chapter_template_vue')