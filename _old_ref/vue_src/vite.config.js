import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  // optimizeDeps: {
  //   include: [
  //     '@ckeditor/ckeditor5-vue',
  //     '@ckeditor/ckeditor5-build-decoupled-document'
  //   ]
  // },
  build: {
    outDir: resolve(__dirname, '../static/vue'),       // Django에서 서빙할 위치
    assetsDir: 'assets',                                // JS/CSS/img 폴더 구조
    // rollupOptions: {
    //   input: resolve(__dirname, 'index.html'),          // Vite entry point
    // },
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]'
      }
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')  // <-- 이 부분이 중요
    }
  }
})
// export default defineConfig({
//   plugins: [vue()],
//   build: {
//     outDir: '../static/vue', // Vue 빌드 결과물이 여기에 생성됨
//     emptyOutDir: true,
//     rollupOptions: {
//       input: path.resolve(__dirname, 'index.html'),
//     }
//   }
// })
