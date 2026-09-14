import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  FrappeUI,
  Button,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  setConfig,
  frappeRequest,
} from 'frappe-ui'

import App from './App.vue'
import router from './router'
import Card from '@/components/Card.vue'
import './index.css'

setConfig('resourceFetcher', frappeRequest)

const globalComponents = {
  Button,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  Card,
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(FrappeUI)

for (const [name, component] of Object.entries(globalComponents)) {
  app.component(name, component)
}

app.mount('#app')
