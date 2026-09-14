// vite.config.js
import vue from "file:///E:/NEXTJS_PROJECTS/EMPLOYEE-TRACKER/frappe-app/hr_portal/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import frappeui from "file:///E:/NEXTJS_PROJECTS/EMPLOYEE-TRACKER/frappe-app/hr_portal/frontend/node_modules/frappe-ui/vite/index.js";
import path from "path";
import { defineConfig } from "file:///E:/NEXTJS_PROJECTS/EMPLOYEE-TRACKER/frappe-app/hr_portal/frontend/node_modules/vite/dist/node/index.js";
var __vite_injected_original_dirname = "E:\\NEXTJS_PROJECTS\\EMPLOYEE-TRACKER\\frappe-app\\hr_portal\\frontend";
var vite_config_default = defineConfig({
  define: {
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false"
  },
  plugins: [
    vue(),
    frappeui({
      frontendRoute: "/hr",
      frappeProxy: true,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: "../hr_portal/public/frontend",
        baseUrl: "/assets/hr_portal/frontend/",
        indexHtmlPath: "../hr_portal/www/hr.html",
        emptyOutDir: true,
        sourcemap: true
      }
    })
  ],
  server: {
    allowedHosts: true
  },
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "src"),
      "tailwind.config.js": path.resolve(__vite_injected_original_dirname, "tailwind.config.js")
    }
  },
  optimizeDeps: {
    include: ["frappe-ui > feather-icons", "feather-icons", "engine.io-client"]
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJFOlxcXFxORVhUSlNfUFJPSkVDVFNcXFxcRU1QTE9ZRUUtVFJBQ0tFUlxcXFxmcmFwcGUtYXBwXFxcXGhyX3BvcnRhbFxcXFxmcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiRTpcXFxcTkVYVEpTX1BST0pFQ1RTXFxcXEVNUExPWUVFLVRSQUNLRVJcXFxcZnJhcHBlLWFwcFxcXFxocl9wb3J0YWxcXFxcZnJvbnRlbmRcXFxcdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL0U6L05FWFRKU19QUk9KRUNUUy9FTVBMT1lFRS1UUkFDS0VSL2ZyYXBwZS1hcHAvaHJfcG9ydGFsL2Zyb250ZW5kL3ZpdGUuY29uZmlnLmpzXCI7aW1wb3J0IHZ1ZSBmcm9tICdAdml0ZWpzL3BsdWdpbi12dWUnXG5pbXBvcnQgZnJhcHBldWkgZnJvbSAnZnJhcHBlLXVpL3ZpdGUnXG5pbXBvcnQgcGF0aCBmcm9tICdwYXRoJ1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcblxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgZGVmaW5lOiB7XG4gICAgX19WVUVfUFJPRF9IWURSQVRJT05fTUlTTUFUQ0hfREVUQUlMU19fOiAnZmFsc2UnLFxuICB9LFxuICBwbHVnaW5zOiBbXG4gICAgdnVlKCksXG4gICAgZnJhcHBldWkoe1xuICAgICAgZnJvbnRlbmRSb3V0ZTogJy9ocicsXG4gICAgICBmcmFwcGVQcm94eTogdHJ1ZSxcbiAgICAgIGx1Y2lkZUljb25zOiB0cnVlLFxuICAgICAgamluamFCb290RGF0YTogdHJ1ZSxcbiAgICAgIGJ1aWxkQ29uZmlnOiB7XG4gICAgICAgIG91dERpcjogJy4uL2hyX3BvcnRhbC9wdWJsaWMvZnJvbnRlbmQnLFxuICAgICAgICBiYXNlVXJsOiAnL2Fzc2V0cy9ocl9wb3J0YWwvZnJvbnRlbmQvJyxcbiAgICAgICAgaW5kZXhIdG1sUGF0aDogJy4uL2hyX3BvcnRhbC93d3cvaHIuaHRtbCcsXG4gICAgICAgIGVtcHR5T3V0RGlyOiB0cnVlLFxuICAgICAgICBzb3VyY2VtYXA6IHRydWUsXG4gICAgICB9LFxuICAgIH0pLFxuICBdLFxuICBzZXJ2ZXI6IHtcbiAgICBhbGxvd2VkSG9zdHM6IHRydWUsXG4gIH0sXG4gIHJlc29sdmU6IHtcbiAgICBhbGlhczoge1xuICAgICAgJ0AnOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCAnc3JjJyksXG4gICAgICAndGFpbHdpbmQuY29uZmlnLmpzJzogcGF0aC5yZXNvbHZlKF9fZGlybmFtZSwgJ3RhaWx3aW5kLmNvbmZpZy5qcycpLFxuICAgIH0sXG4gIH0sXG4gIG9wdGltaXplRGVwczoge1xuICAgIGluY2x1ZGU6IFsnZnJhcHBlLXVpID4gZmVhdGhlci1pY29ucycsICdmZWF0aGVyLWljb25zJywgJ2VuZ2luZS5pby1jbGllbnQnXSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQWlZLE9BQU8sU0FBUztBQUNqWixPQUFPLGNBQWM7QUFDckIsT0FBTyxVQUFVO0FBQ2pCLFNBQVMsb0JBQW9CO0FBSDdCLElBQU0sbUNBQW1DO0FBS3pDLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLFFBQVE7QUFBQSxJQUNOLHlDQUF5QztBQUFBLEVBQzNDO0FBQUEsRUFDQSxTQUFTO0FBQUEsSUFDUCxJQUFJO0FBQUEsSUFDSixTQUFTO0FBQUEsTUFDUCxlQUFlO0FBQUEsTUFDZixhQUFhO0FBQUEsTUFDYixhQUFhO0FBQUEsTUFDYixlQUFlO0FBQUEsTUFDZixhQUFhO0FBQUEsUUFDWCxRQUFRO0FBQUEsUUFDUixTQUFTO0FBQUEsUUFDVCxlQUFlO0FBQUEsUUFDZixhQUFhO0FBQUEsUUFDYixXQUFXO0FBQUEsTUFDYjtBQUFBLElBQ0YsQ0FBQztBQUFBLEVBQ0g7QUFBQSxFQUNBLFFBQVE7QUFBQSxJQUNOLGNBQWM7QUFBQSxFQUNoQjtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTztBQUFBLE1BQ0wsS0FBSyxLQUFLLFFBQVEsa0NBQVcsS0FBSztBQUFBLE1BQ2xDLHNCQUFzQixLQUFLLFFBQVEsa0NBQVcsb0JBQW9CO0FBQUEsSUFDcEU7QUFBQSxFQUNGO0FBQUEsRUFDQSxjQUFjO0FBQUEsSUFDWixTQUFTLENBQUMsNkJBQTZCLGlCQUFpQixrQkFBa0I7QUFBQSxFQUM1RTtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
