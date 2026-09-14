import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'path'
import { defineConfig } from 'vite'

export default defineConfig({
  define: {
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
  plugins: [
    vue(),
    frappeui({
      frontendRoute: '/hr',
      frappeProxy: false,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: '../hr_portal/public/frontend',
        baseUrl: '/assets/hr_portal/frontend/',
        indexHtmlPath: '../hr_portal/www/hr.html',
        emptyOutDir: true,
        sourcemap: true,
      },
    }),
  ],
  server: {
    allowedHosts: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      'tailwind.config.js': path.resolve(__dirname, 'tailwind.config.js'),
    },
  },
  optimizeDeps: {
    include: ['frappe-ui > feather-icons', 'feather-icons', 'engine.io-client'],
  },
})
