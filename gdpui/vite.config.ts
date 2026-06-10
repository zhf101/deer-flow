import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue2";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const isVsExt = mode === "vsext";

  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    // 嵌入 VSCode webview 时使用相对路径
    base: isVsExt ? "./" : "/",
    server: {
      port: 5180,
      // 本地开发阶段禁用浏览器缓存，避免 Vite 动态模块缓存损坏后反复触发加载失败
      headers: {
        "Cache-Control": "no-store",
      },
      proxy: {
        // 后端 Gateway,默认本地 8001(与 deer-flow 约定一致)
        "/api": {
          target: "http://127.0.0.1:8001",
          changeOrigin: true,
          // 登录/注册接口会校验 Origin，需要把浏览器访问的原始来源转给后端
          xfwd: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
    },
  };
});
