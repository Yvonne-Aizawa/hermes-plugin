import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: 'src/main.ts',
      name: 'LuminaDashboardPlugin',
      formats: ['iife'],
      fileName: () => 'index.js',
    },
  },
})
