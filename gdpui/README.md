# web-client (gdpui)

基于 **Vue 2.7 + TypeScript + Vite 6** 的前端基础框架。

## 技术栈

| 分类 | 选型 |
|---|---|
| 框架 | Vue 2.7.16(Composition API + `<script setup>`)+ TypeScript 5.8 |
| 构建 | Vite 6 + `@vitejs/plugin-vue2` |
| 路由 | Vue Router 3 |
| 状态 | Pinia 2 + `pinia-plugin-persistedstate`(持久化) |
| UI | Element UI 2.x(Vue 2 版） |
| 样式 | Tailwind CSS 4(`@tailwindcss/vite`，CSS-first 配置）+ Sass |
| 图标 | FontAwesome(`vue-fontawesome` 2.x） |
| HTTP | 原生 `fetch` 封装(`src/api/http.ts`，无 axios 依赖） |
| 工程化 | vue-tsc / ESLint 9 / oxlint / Prettier / Vitest |

## 目录结构

```
gdpui/
├── index.html              # 入口 HTML
├── vite.config.ts          # Vite 配置(含 @ 别名、/api 代理、vsext 模式)
├── tsconfig*.json          # TS 工程引用配置
├── env.d.ts                # 环境变量与 *.vue 类型声明
├── eslint.config.ts        # ESLint flat config
└── src/
    ├── main.ts             # 应用入口(注册 Element UI / FontAwesome / Pinia / Router)
    ├── App.vue             # 根组件
    ├── api/                # HTTP 客户端封装
    ├── assets/styles/      # 全局样式(Tailwind 入口 + 项目样式)
    ├── router/             # 路由定义
    ├── stores/             # Pinia store
    └── views/              # 页面视图
```

## 常用命令

```bash
npm install          # 安装依赖

npm run dev          # 开发服务器(默认 http://localhost:5180)
npm run dev:vsext    # VSCode webview 模式(相对路径 base)

npm run type-check   # vue-tsc 类型检查
npm run build        # 类型检查 + 生产构建 → dist/
npm run preview      # 预览生产构建

npm run lint         # oxlint + eslint 修复
npm run format       # prettier 格式化 src/
npm run test:unit    # vitest 单元测试
```

## 配置说明

- **API 代理**:`vite.config.ts` 中 `/api` 默认代理到 `http://127.0.0.1:8001`(deer-flow Gateway)。
- **环境变量**:复制 `.env.example` 调整 `VITE_API_BASE_URL`。开发默认值在 `.env.development`。
- **Tailwind v4**:无 `tailwind.config.js` / `postcss.config.js`，在 `src/assets/styles/main.scss` 中通过 `@import "tailwindcss"` 引入，主题用 `@theme` 在 CSS 中定义。


## 目标
需要把gdpui项目做成一个多标签页 / 多页签 (Multi-Tab)页签式导航的后台管理系统界面,
可以重点参考 vue-element-admin (本地路径 D:\code\vue-element-admin )这类开源项目的源码，看看它们是如何集成和管理多标签页的。
把frontend项目的gdp相关页面都迁移到gdpui项目里面, 注意一个关键点——frontend 是 Next.js(React),
gdpui 是 Vue 2,所以"迁移"实质是跨框架重写,不是复制。