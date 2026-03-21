# DeerFlow Offline Development Environment

Docker Compose 文件分为三个用途：

## 文件说明

| 文件 | 用途 |
|------|------|
| `docker-compose-build.yaml` | **构建镜像** - 只构建，不运行 |
| `docker-compose-dev.yaml` | **正常运行** - 启动开发环境 |
| `docker-compose-debug.yaml` | **调试模式** - 启动调试环境 + VS Code Server |

---

## 快速开始

### 1. 构建镜像

```powershell
# 构建所有镜像
docker-compose -f docker/docker-compose-build.yaml build
```

### 2. 正常运行（不带调试）

```powershell
# 启动开发环境
docker-compose -f docker/docker-compose-dev.yaml up -d

# 访问
#   主应用: http://localhost:2026
```

### 3. 调试模式

```powershell
# 启动调试环境（包含 VS Code Server）
docker-compose -f docker/docker-compose-debug.yaml up -d

# 访问
#   主应用: http://localhost:2026
#   VS Code IDE: http://localhost:8080 (密码: deerflow)
```

---

## 调试步骤

### 端口映射

| 服务 | 应用端口 | 调试端口 |
|------|----------|----------|
| Gateway | 8001 | **5678** |
| LangGraph | 2024 | **5679** |
| Code Server | 8080 | - |

### 调试流程

1. 启动调试模式：
   ```powershell
   docker-compose -f docker/docker-compose-debug.yaml up -d
   ```

2. 打开 VS Code IDE：`http://localhost:8080`

3. Gateway/LangGraph 会等待调试器连接：
   ```
   [Gateway] debugpy waiting for attach on port 5678...
   ```

4. 在 VS Code 中选择调试配置：
   - **Debug Gateway (Docker Attach)** - 调试 Gateway
   - **Debug LangGraph (Docker Attach)** - 调试 LangGraph

5. 按 `F5` 开始调试，服务会继续启动

---

## 离线部署

### 联网机器导出

```powershell
.\scripts\export-dev-images.ps1
```

导出目录：`dev-images/`

### 离线机器导入

```powershell
.\scripts\import-dev-images.ps1
```

然后启动：
```powershell
docker-compose -f docker/docker-compose-debug.yaml up -d
```

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Network (deer-flow-dev)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐         ┌──────────────┐                     │
│  │ Code Server  │         │   Gateway    │                     │
│  │   (8080)     │────────▶│  (8001)      │                     │
│  │              │  attach │  debug:5678  │                     │
│  │  VS Code IDE │         └──────────────┘                     │
│  │  + debugpy   │         ┌──────────────┐                     │
│  │   extension  │────────▶│  LangGraph   │                     │
│  └──────────────┘  attach │  (2024)      │                     │
│                          │  debug:5679   │                     │
│                          └──────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 预安装的 VS Code 扩展

- **ms-python.python** - Python 语言支持
- **ms-python.debugpy** - Python 调试器
- **ms-python.vscode-pylance** - Python 类型检查
- **eamodio.gitlens** - Git 增强
- **esbenp.prettier-vscode** - 代码格式化
- **dbaeumer.vscode-eslint** - ESLint
- **bradlc.vscode-tailwindcss** - Tailwind CSS
- **ms-azuretools.vscode-docker** - Docker 支持
- **redhat.vscode-yaml** - YAML 支持