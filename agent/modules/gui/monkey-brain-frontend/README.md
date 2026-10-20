# 🧠 Monkey Brain Segmentation Frontend

## 项目简介
这是一个基于React + TypeScript + Vite的现代化前端应用，用于猴脑分割和神经影像分析。

## 主要功能
- 🔐 用户认证和会话管理
- 📁 NIfTI文件上传和处理
- 🧠 3D脑影像可视化
- 🤖 AI Agent对话界面
- ⚙️ 分割参数配置
- 📊 任务管理和结果展示

## 技术栈
- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **状态管理**: Zustand
- **样式**: Tailwind CSS
- **3D可视化**: NiiVue
- **HTTP客户端**: Axios

## 项目结构
```
src/
├── components/          # 组件
│   ├── Agent/          # AI对话组件
│   ├── Auth/           # 认证组件
│   ├── Config/         # 配置组件
│   ├── FileUpload/     # 文件上传组件
│   ├── Layout/         # 布局组件
│   ├── Segmentation/   # 分割相关组件
│   └── Visualization/  # 可视化组件
├── pages/              # 页面
├── services/           # API服务
├── stores/             # 状态管理
├── types/              # 类型定义
├── utils/              # 工具函数
└── styles/             # 样式文件
```

## 快速开始

### 本地开发
```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

### Singularity 容器部署（推荐用于服务器）

```bash
# 1. 上传项目到服务器
scp -r monkey-brain-frontend user@server:/path/to/destination/

# 2. 在服务器上运行部署脚本
cd monkey-brain-frontend
chmod +x singularity-deploy.sh
./singularity-deploy.sh

# 3. 访问应用
# SSH 端口转发示例（端口可变）:
# ssh -L 5173:localhost:5173 user@server
# 然后访问: http://localhost:5173
```

**详细说明请查看** `QUICK_START_SINGULARITY.md`

## 环境配置
复制 `.env.example` 到 `.env` 并配置相应的环境变量（可选）：

```bash
cp .env.example .env
```

## 主要页面
- **登录页面** (`/login`) - 用户认证
- **仪表板** (`/`) - 主控制面板
- **分割页面** (`/segmentation`) - 脑分割功能
- **Pipeline 页面** (`/pipeline`) - 预处理/分割/重建流程编排
- **可视化页面** (`/visualization`) - 3D脑影像查看
- **配置页面** (`/config`) - 参数设置

## 开发指南
- 使用TypeScript进行类型安全开发
- 遵循React Hooks最佳实践
- 使用Zustand进行状态管理
- 组件采用函数式编程风格
- 样式使用Tailwind CSS工具类

## Pipeline 后端对接

Pipeline 页面通过 `/api/pipeline/*` 调用后端执行 `primx`。后端端口会自动探测空闲端口（默认从 8000 起），并写入 `public/ports.json` 供前端读取：

```bash
primx=workflows/primx_cli/primx
singularity exec $container $primx gui start-backend
```

也可以一次启动前端 + 后端：

```bash
singularity exec $container $primx gui start-stack
```

## 📚 部署文档

- **`QUICK_START_SINGULARITY.md`** - Singularity 快速开始（3 步部署）
- **`SINGULARITY_DEPLOYMENT.md`** - Singularity 完整部署指南
- **`SERVER_DEPLOYMENT_GUIDE.md`** - 通用服务器部署指南

## 🔐 访问令牌与认证

当使用 `primx gui start-stack` 启动时，会自动生成访问令牌并在控制台输出。请在访问地址后追加 `?token=...`：

```
http://<HOST>:<FRONTEND_PORT>/?token=<PRIMX_ACCESS_TOKEN>
```

该令牌用于前端请求后端 API 的授权头部（Authorization）。

## 🌐 访问地址

部署后的默认访问地址（端口可自动变化）：

- **本地访问**: `http://localhost:<FRONTEND_PORT>`
- **SSH 端口转发**: 
  ```bash
  ssh -L <FRONTEND_PORT>:localhost:<FRONTEND_PORT> user@server
  # 然后访问 http://localhost:<FRONTEND_PORT>
  ```
- **直接访问**: `http://服务器IP:<FRONTEND_PORT>`

## 端口自动选择与运行时配置

为避免多用户在同一台机器上端口冲突，前端与后端会自动选择空闲端口并写入 `public/ports.json`：

```
{
  "pipelinePort": "8000",
  "agentPort": "8100",
  "frontendPort": "5173"
}
```

前端运行时会读取 `ports.json` 来定位 pipeline 与 agent 后端，不需要手动修改代码。

默认情况下，前端使用同源 API 模式：浏览器只访问当前网站域名，Vite 前端服务在服务器内部把 API
请求转发到 pipeline/agent 后端。因此无论用户来自局域网、校外、国内还是国外，都不需要直接访问
`8000`/`8100` 等后端端口：

```
browser -> https://primatex.pku.edu.cn/api/agent/* -> Vite proxy -> agent backend (<AGENT_PORT>)
browser -> https://primatex.pku.edu.cn/api/*       -> Vite proxy -> pipeline backend (<PIPELINE_PORT>)
```

如果另有 Nginx/Apache 反向代理，也可以直接在 Web 服务器上做同样转发。`/api/agent/` 规则必须放在
通用 `/api/` 规则前面。

默认启动即可：

```
primx gui start
```

如需恢复旧的浏览器直连后端端口模式（仅适合局域网或 SSH 端口转发），使用：

```
primx gui start --direct-api
```

### 可选环境变量（覆盖自动端口）
- `PIPELINE_PORT`: pipeline 后端起始端口（默认 8000）
- `AGENT_PORT`: agent 后端起始端口（默认 8100）
- `VITE_DEV_PORT` / `PORT`: 前端起始端口（默认 5173）
- `VITE_PIPELINE_API` / `VITE_PIPELINE_PORT`: 前端强制指定 pipeline 地址/端口
- `VITE_AGENT_BACKEND_URL` / `VITE_AGENT_BACKEND_PORT`: 前端强制指定 agent 地址/端口
- `PRIMX_SAME_ORIGIN_API`: 默认 `1`，前端对 pipeline/agent 都使用当前域名同源 API；设为 `0` 可恢复直连端口
- `PRIMX_PIPELINE_BASE_URL` / `PRIMX_AGENT_BASE_URL`: 写入 `ports.json` 的运行时后端完整地址

## 部署方式

项目支持多种部署方式：
- **Singularity 容器**（推荐用于 HPC 集群和服务器）
- **Docker 容器**
- **传统 Web 服务器**（Nginx + Node.js）
- **云平台**（Vercel, Netlify）

构建后的文件在 `dist/` 目录中。
