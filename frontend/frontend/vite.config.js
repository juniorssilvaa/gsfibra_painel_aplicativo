// vite.config.js - Configuração para produção
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Carregar variáveis de ambiente do diretório backend
  // Carregar todas as variáveis para buscar SUPABASE_URL e SUPABASE_ANON_KEY
  const allEnv = loadEnv(mode, '../../backend', '');
  const viteEnv = loadEnv(mode, '../../backend', 'VITE_');
  
  // Plugin para injetar variáveis do backend como VITE_
  const injectEnvPlugin = () => ({
    name: 'inject-backend-env',
    config(config) {
      // Mapear SUPABASE_URL e SUPABASE_ANON_KEY para VITE_ se não existirem
      if (!viteEnv.VITE_SUPABASE_URL && allEnv.SUPABASE_URL) {
        config.define = config.define || {};
        config.define['import.meta.env.VITE_SUPABASE_URL'] = JSON.stringify(allEnv.SUPABASE_URL);
      }
      if (!viteEnv.VITE_SUPABASE_ANON_KEY && allEnv.SUPABASE_ANON_KEY) {
        config.define = config.define || {};
        config.define['import.meta.env.VITE_SUPABASE_ANON_KEY'] = JSON.stringify(allEnv.SUPABASE_ANON_KEY);
      }
    }
  });
  
  return {
    envDir: '../../backend',
    base: '/',
    plugins: [react(), tailwindcss(), injectEnvPlugin()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
        "react": path.resolve(__dirname, "./node_modules/react"),
        "react-dom": path.resolve(__dirname, "./node_modules/react-dom"),
        "react-dom/client": path.resolve(__dirname, "./node_modules/react-dom/client"),
        "react/jsx-runtime": path.resolve(__dirname, "./node_modules/react/jsx-runtime"),
        "react/jsx-dev-runtime": path.resolve(__dirname, "./node_modules/react/jsx-dev-runtime"),
      },
      dedupe: ['react', 'react-dom', 'react-dom/client'],
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.json']
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      minify: 'terser',
      rollupOptions: {
        output: {
          manualChunks: {
            ui: ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu']
          }
        }
      },
      commonjsOptions: {
        transformMixedEsModules: true
      }
    },
    optimizeDeps: {
      exclude: ['pdfjs-dist'],
      include: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime'],
      force: true,
      esbuildOptions: {
        define: {
          global: 'globalThis'
        }
      }
    },
    server: {
      host: '0.0.0.0',
      port: 8012,
      strictPort: true,
      allowedHosts: ['chat.niohub.com.br'],
      cors: true,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
        'Access-Control-Allow-Headers': 'X-Requested-With, content-type, Authorization'
      },
      proxy: {
        '/api': {
          target: 'http://localhost:8010',
          changeOrigin: true,
          secure: false
        },
        '/api-token-auth': {
          target: 'http://localhost:8010',
          changeOrigin: true,
          secure: false
        },
        '/auth': {
          target: 'http://localhost:8010/api',
          changeOrigin: true,
          secure: false
        },
        '/webhook': {
          target: 'http://localhost:8010',
          changeOrigin: true,
          secure: false
        },
        '/webhooks': {
          target: 'http://localhost:8010',
          changeOrigin: true,
          secure: false
        },
        '/media': {
          target: 'http://localhost:8010',
          changeOrigin: true,
          secure: false
        },
        // Proxy para WebSocket
        '/ws': {
          target: 'ws://localhost:8010',
          ws: true,
          changeOrigin: true,
          secure: false
        }
      }
    }
  }
})
