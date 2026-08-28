// vite.config.js - Configuração para produção
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Carregar variáveis de ambiente do diretório backend
  // Carregar todas as variáveis para buscar SUPABASE_URL e SUPABASE_ANON_KEY
  const allEnv = loadEnv(mode, '../backend', '');
  const viteEnv = loadEnv(mode, '../backend', 'VITE_');
  
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
    envDir: '../backend',
    base: '/',
    plugins: [react(), tailwindcss(), injectEnvPlugin()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
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
            vendor: ['react', 'react-dom', 'react-router-dom'],
            charts: ['chart.js', 'react-chartjs-2', 'recharts'],
            supabase: ['@supabase/supabase-js'],
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
      include: [
        'react',
        'react-dom',
        'react-dom/client',
        'react/jsx-runtime',
        'react/jsx-dev-runtime',
        'react-router-dom',
      ],
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
      allowedHosts: ['chat-local.niohub.com.br', 'localhost'],
      cors: true,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
        'Access-Control-Allow-Headers': 'X-Requested-With, content-type, Authorization'
      },
      proxy: {
        '^/api/voice-calls/events': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false,
          proxyTimeout: 0,
          timeout: 0,
        },
        '/api': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false
        },
        '/api-token-auth': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false
        },
        '/auth': {
          target: 'http://localhost:8011/api',
          changeOrigin: true,
          secure: false
        },
        '/webhook': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false
        },
        '/webhooks': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false
        },
        '/media': {
          target: 'http://localhost:8011',
          changeOrigin: true,
          secure: false
        },
        '/ws': {
          target: 'ws://localhost:8011',
          ws: true,
          changeOrigin: true,
          secure: false
        }
      }
    }
  }
})
