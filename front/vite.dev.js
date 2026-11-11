import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  const envDir = path.resolve(__dirname)
  const allEnv = loadEnv(mode, envDir, '')
  const viteEnv = loadEnv(mode, envDir, 'VITE_')

  const injectEnvPlugin = () => ({
    name: 'inject-backend-env',
    config(config) {
      if (!viteEnv.VITE_SUPABASE_URL && allEnv.SUPABASE_URL) {
        config.define = config.define || {}
        config.define['import.meta.env.VITE_SUPABASE_URL'] = JSON.stringify(allEnv.SUPABASE_URL)
      }
      if (!viteEnv.VITE_SUPABASE_ANON_KEY && allEnv.SUPABASE_ANON_KEY) {
        config.define = config.define || {}
        config.define['import.meta.env.VITE_SUPABASE_ANON_KEY'] = JSON.stringify(allEnv.SUPABASE_ANON_KEY)
      }
    },
  })

  return {
    envDir,
    base: '/',
    plugins: [react(), tailwindcss(), injectEnvPlugin()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
        '@gsfibra': path.resolve(__dirname, './src'),
      },
      dedupe: ['react', 'react-dom', 'react-dom/client'],
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      minify: false,
      commonjsOptions: { transformMixedEsModules: true },
    },
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'react-dom/client',
        'react/jsx-runtime',
        'react/jsx-dev-runtime',
        'react-router-dom',
      ],
      esbuildOptions: { define: { global: 'globalThis' } },
    },
    server: {
      host: '0.0.0.0',
      port: 8014,
      strictPort: false,
      allowedHosts: ['gsfibra.niohub.com.br', 'localhost', '127.0.0.1'],
      cors: true,
      proxy: {
        '/api': { target: 'http://localhost:8010', changeOrigin: true, secure: false, ws: false },
        '/api-token-auth': { target: 'http://localhost:8010', changeOrigin: true, secure: false },
        '/auth': { target: 'http://localhost:8010/api', changeOrigin: true, secure: false },
        '/media': { target: 'http://localhost:8010', changeOrigin: true, secure: false },
        '/ws': { target: 'ws://localhost:8010', ws: true, changeOrigin: true, secure: false },
      },
    },
  }
})
