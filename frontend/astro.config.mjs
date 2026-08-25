import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';

// https://astro.build/config
export default defineConfig({
  integrations: [
    react(),
    tailwind({
      applyBaseStyles: false,
    }),
  ],
  server: {
    port: 4321,
    proxy: {
      '/api': {
        target: process.env.ARIA_API_URL || 'http://127.0.0.1:8001',
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (proxyReq, _req, _res) => {
            const apiKey = process.env.ARIA_API_KEY || process.env.API_KEY;
            if (apiKey) {
              proxyReq.setHeader('X-API-Key', apiKey);
            }
          });
        },
      },
    },
  },
  vite: {
    optimizeDeps: {
      include: ['reactflow', 'dagre', 'react-markdown', 'remark-gfm', 'lucide-react', 'framer-motion'],
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('reactflow') || id.includes('@reactflow') || id.includes('dagre')) {
                return 'vendor-graphs';
              }
              if (id.includes('react-markdown') || id.includes('remark') || id.includes('micromark') || id.includes('unified') || id.includes('mdast') || id.includes('unist')) {
                return 'vendor-markdown';
              }
              if (id.includes('lucide-react')) {
                return 'vendor-icons';
              }
              if (id.includes('framer-motion')) {
                return 'vendor-motion';
              }
            }
          },
        },
      },
    },
  },
});
