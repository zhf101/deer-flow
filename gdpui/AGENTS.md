下面是一份优化后的提示词，你可以直接用它来指导开发人员（或AI）完成 **gdpui 后台管理系统的多标签页集成** 以及 **从 frontend (Next.js/React) 到 gdpui (Vue 2) 的页面迁移**。提示词重点强调了跨框架重写时容易遗漏的组件、布局和交互细节，并提供了检查清单。

---

## 项目任务提示词（完整版）

### 一、总体目标

将 `gdpui` 项目改造为 **多标签页（Multi-Tab）页签式导航的后台管理系统**，并参考 `vue-element-admin`（本地路径 `D:\code\vue-element-admin`）中多标签页的实现方式。  
同时，将 `frontend` 项目（Next.js + React）中所有与 **GDP 相关的页面** 迁移到 `gdpui`（Vue 2）中。  
**注意**：这不是代码复制，而是**跨框架重写** —— 需要根据原 React 页面的业务逻辑、UI 结构和交互行为，用 Vue 2 的语法和技术栈重新实现。

---

### 二、多标签页集成（参考 vue-element-admin）

请仔细阅读 `vue-element-admin` 源码中以下模块，理解其多标签页的工作机制，并在 `gdpui` 中实现类似功能：

#### 关键参考点
1. **标签页状态管理**  
   - 使用 Vuex 存储 `visitedViews`（已打开的标签页数组）和 `cachedViews`（需要缓存的页面组件名）。  
   - 提供 mutations/actions：`addView`、`delView`、`delOthersViews`、`delAllViews` 等。

2. **路由与标签页联动**  
   - 监听路由变化（`$route`），自动将当前路由添加到标签页。  
   - 根据路由的 `meta.title` 和 `meta.icon` 显示标签页标题和图标。  
   - 关闭标签页时，自动跳转到最后一个活跃标签页或默认首页。

3. **标签页组件实现**  
   - 开发 `<tags-view>` 组件，支持：  
     - 横向滚动（当标签过多时）  
     - 右键菜单（关闭当前/其他/全部）  
     - 点击标签页切换路由  
     - 拖拽排序（可选）  
   - 样式参考 `vue-element-admin` 的 `src/layout/components/TagsView/index.vue`。

4. **页面缓存（keep-alive）**  
   - 使用 `<keep-alive :include="cachedViews">` 包裹 `<router-view>`，确保已关闭的页面不再缓存。  
   - 根据路由 `meta.keepAlive` 决定是否加入缓存。

5. **与面包屑集成**  
   - 标签页切换时，同步更新面包屑导航（若项目已有面包屑）。

#### 实现时注意
- 确保标签页在刷新浏览器后能够恢复（结合 `localStorage` 或 `sessionStorage` 保存 `visitedViews`）。  
- 对于动态路由（如 `/detail/:id`），应支持不同参数对应不同标签页（例如 `/detail/1` 和 `/detail/2` 是两个独立标签）。可使用路由的 `fullPath` 作为标签页的唯一标识。

---

### 三、页面迁移：frontend (React) → gdpui (Vue 2)

`frontend` 项目是一个 Next.js + React 应用，其 GDP 相关页面分散在多个路由和组件中。迁移时**必须**完整保留原页面的所有功能、布局和交互细节。  

#### 3.1 迁移前置工作
1. **梳理页面清单**  
   列出 `frontend` 中所有 GDP 相关的页面路由和组件：  
   - 例如：`/gdp/overview`、`/gdp/trend`、`/gdp/compare`、`/gdp/table`、`/gdp/detail/:id` 等。  
   - 同时记录每个页面依赖的子组件（图表、表格、筛选栏、弹窗等）。

2. **分析布局结构**  
   - `frontend` 的 Layout 可能包含侧边栏、顶部导航、内容区域等。  
   - 迁移时需在 `gdpui` 中定义对应的 Layout（推荐使用 `vue-element-admin` 的 Layout 结构，并替换为 GDP 所需的模块）。  
   - 注意：全局布局中的**头部的用户菜单、通知中心、侧边栏菜单**等也要一起迁移，不能遗漏。

#### 3.2 重写时的逐项对照清单（防遗漏）

请按以下维度逐一检查原 React 页面，确保 Vue 版本完全覆盖：

##### ✅ 组件结构
- [ ] 页面主组件（page container）  
- [ ] 拆分的子组件（如筛选表单、图表卡片、数据表格、分页器）  
- [ ] 弹窗组件（Modal / Dialog / Drawer）及其打开/关闭逻辑  
- [ ] 公共组件（如 Loading、Empty、ErrorBoundary 等）在 Vue 中的替代实现

##### ✅ 布局与样式
- [ ] 页面的栅格布局（flex/grid）  
- [ ] 响应式断点（移动端适配，若原项目有）  
- [ ] 间距、边框、圆角等视觉细节（可复用 `gdpui` 现有 UI 库，如 Element UI）  
- [ ] 滚动条样式、固定表头、吸顶筛选栏等特殊布局效果

##### ✅ 交互与行为
- [ ] 表单输入及校验（React 中可能是 Formik + Yup → Vue 中可用 VeeValidate 或 Element UI 表单验证）  
- [ ] 异步数据加载的 loading 状态（骨架屏或转圈动画）  
- [ ] 错误提示（toast / message / 全局错误捕获）  
- [ ] 分页、排序、筛选（前端或后端实现）  
- [ ] 图表的渲染与更新（ECharts / Highcharts → 使用 Vue 封装组件）  
- [ ] 导出/导入功能（Excel、CSV）  
- [ ] 复制粘贴、快捷键（若有）  
- [ ] 拖拽排序、拖拽上传等

##### ✅ 路由与参数
- [ ] 路由参数（`query` 和 `params`）的读取与监听  
- [ ] 路由跳转（`router.push` 替换 `next/router`）  
- [ ] 路由守卫中的权限检查（如页面要求特定角色）  
- [ ] 历史记录回退时的状态恢复（例如筛选条件保留）

##### ✅ 状态管理
- [ ] 原 React 中使用的 Context / Redux / Zustand 等状态 → 迁移到 Vuex 模块  
- [ ] 页面级别的本地状态（`useState` → `data` + `computed`）  
- [ ] 副作用（`useEffect` → `watch` / `mounted` / `beforeDestroy`）  
- [ ] 跨组件共享的全局状态（如用户信息、GDP 数据筛选条件）

##### ✅ 生命周期与性能
- [ ] 组件挂载时请求数据（`useEffect` → `mounted`）  
- [ ] 组件卸载时的清理（取消请求、清除定时器）  
- [ ] 使用 `computed` 代替 React 的 `useMemo`  
- [ ] 使用 `watch` 代替 `useEffect` 监听特定 prop 变化  
- [ ] 列表渲染的 `key` 处理（Vue 使用 `:key`）

##### ✅ 辅助功能与边缘情况
- [ ] 页面标题（document.title）的动态设置  
- [ ] 权限控制（按钮级/菜单级）  
- [ ] 国际化（若原项目有 i18n）  
- [ ] 暗黑模式（若原项目支持）  
- [ ] 大数据量表格的虚拟滚动  
- [ ] WebSocket 实时更新（若有）

#### 3.3 迁移后的验证
每迁移完一个页面，必须：
1. **视觉对比**：在相同分辨率下对比 React 原版和 Vue 新版，确保布局、间距、颜色、字体一致。  
2. **功能对比**：逐一测试所有用户操作（点击、输入、提交、下载等），结果应相同。  
3. **异常场景**：网络断开、接口报错、表单必填项空缺、权限不足等提示应与原版一致。  
4. **性能**：页面切换、数据加载、图表渲染的响应速度不应明显劣于原版。

---

### 四、常见遗漏项专项检查（跨框架重写易忽略）

请特别注意以下经常被遗漏的点：

1. **全局样式的影响**  
   - React 中的全局 CSS 可能通过 `index.css` 或 CSS-in-JS 定义了一些 reset 或通用类（如 `.container`、`.flex-between`）。Vue 项目中需要复制或重写这些样式，否则页面看起来“散架”。

2. **第三方库的初始化与销毁**  
   - 例如 ECharts 实例需要在 `beforeDestroy` 中调用 `dispose()`，避免内存泄漏。  
   - 原 React 中可能在 `useEffect` 的 cleanup 函数中移除事件监听，Vue 中对应 `beforeDestroy`。

3. **滚动位置恢复**  
   - 多标签页切换时，滚动条位置应保留（特别是表格和列表页）。可使用 `<keep-alive>` 配合 `scrollBehavior` 或自定义指令实现。

4. **表单数据持久化**  
   - 原项目可能使用 `localStorage` 暂存用户填写的表单内容（如草稿）。迁移时需保留相同逻辑。

5. **浏览器前进/后退按钮行为**  
   - 在 Vue Router 中，需确保通过浏览器后退时，标签页高亮对应正确，且页面状态（如筛选条件）与历史记录匹配。

6. **路由 meta 字段的完整迁移**  
   - 原 React 路由配置中可能包含 `title`、`icon`、`hidden`、`roles`、`keepAlive` 等元数据，必须在 Vue Router 中全部保留。

7. **微交互细节**  
   - 按钮 loading 状态（防止重复提交）  
   - 输入框防抖/节流（搜索框）  
   - 表格行的悬停效果、点击复制提示  
   - 图表 tooltip 格式、空数据占位图

8. **错误边界和降级**  
   - React 中的 `componentDidCatch` 或 `ErrorBoundary` 组件，Vue 中可以使用 `errorCaptured` 钩子或全局 `errorHandler` 实现类似效果。

---

### 五、推荐实施步骤

1. **环境准备**  
   - 确认 `gdpui` 已安装 Vue 2、Vue Router、Vuex、Element UI（或你使用的 UI 库）、axios 等基础依赖。  
   - 引入 `vue-element-admin` 的 Layout 结构（或参考其 tags-view 组件独立实现）。

2. **多标签页基础设施**  
   - 编写 Vuex 模块（`tagsView`）和相关组件。  
   - 修改 Layout 中的 `<router-view>` 包裹 `<keep-alive>` 和 `tags-view` 组件。  
   - 测试标签页的基本功能（打开、关闭、切换、刷新恢复）。

3. **迁移公共部分**  
   - 将 `frontend` 中的 API 服务层（GDP 相关的接口调用）用 Vue 方式重写。  
   - 迁移全局状态（如用户信息、权限）。  
   - 迁移全局样式、主题变量。

4. **逐个迁移页面**  
   - 按依赖程度从低到高迁移（先独立页面，后相互引用的页面）。  
   - 每迁移一个页面，对照第三部分的检查清单进行自测。  
   - 提交代码并标记已完成。

5. **集成测试与回归**  
   - 测试多标签页下所有页面相互切换时的状态保持。  
   - 测试关闭标签页后重新打开，缓存是否正常。  
   - 测试路由权限、动态菜单等高级功能。

6. **性能优化**  
   - 对图表组件使用 `v-once` 或懒加载。  
   - 使用 `webpack-bundle-analyzer` 分析打包体积，按需加载 GDP 页面模块。
