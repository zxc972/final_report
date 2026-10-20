# 📦 仅安装依赖指南

如果你只想安装依赖而不使用 Singularity 容器，可以按照以下步骤操作。

---

## 🚀 快速安装

### 方法 1: 使用 npm（推荐）

```bash
cd monkey-brain-frontend
npm install
```

### 方法 2: 使用 yarn

```bash
cd monkey-brain-frontend
yarn install
```

### 方法 3: 使用 pnpm

```bash
cd monkey-brain-frontend
pnpm install
```

---

## 📋 详细步骤

### 步骤 1: 检查 Node.js 环境

```bash
# 检查 Node.js 版本（需要 16+，推荐 18+）
node --version

# 检查 npm 版本
npm --version
```

如果没有安装 Node.js，请先安装：

**Ubuntu/Debian:**
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**CentOS/RHEL:**
```bash
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo yum install -y nodejs
```

**macOS:**
```bash
brew install node@18
```

### 步骤 2: 进入项目目录

```bash
cd monkey-brain-frontend
```

### 步骤 3: 安装依赖

```bash
# 标准安装
npm install

# 或者使用 ci 命令（更快，适合 CI/CD）
npm ci

# 或者只安装生产依赖
npm install --production
```

### 步骤 4: 验证安装

```bash
# 检查 node_modules 目录
ls -la node_modules/

# 查看已安装的包
npm list --depth=0
```

---

## ⚙️ 安装选项

### 仅安装生产依赖

```bash
npm install --production
# 或
npm ci --only=production
```

### 清理后重新安装

```bash
# 删除 node_modules 和 package-lock.json
rm -rf node_modules package-lock.json

# 重新安装
npm install
```

### 使用国内镜像加速（中国用户）

```bash
# 使用淘宝镜像
npm install --registry=https://registry.npmmirror.com

# 或永久设置
npm config set registry https://registry.npmmirror.com
npm install
```

---

## 🔧 常见问题

### Q1: 安装速度很慢怎么办？

**方法 A: 使用国内镜像**
```bash
npm config set registry https://registry.npmmirror.com
npm install
```

**方法 B: 使用 pnpm（更快）**
```bash
npm install -g pnpm
pnpm install
```

**方法 C: 使用 yarn**
```bash
npm install -g yarn
yarn install
```

### Q2: 权限错误怎么办？

```bash
# 不要使用 sudo，而是修复 npm 权限
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# 然后重新安装
npm install
```

### Q3: 依赖冲突怎么办？

```bash
# 使用 --legacy-peer-deps
npm install --legacy-peer-deps

# 或使用 --force
npm install --force
```

### Q4: 磁盘空间不足怎么办？

```bash
# 清理 npm 缓存
npm cache clean --force

# 删除不需要的包
npm prune

# 然后重新安装
npm install
```

### Q5: 网络连接失败怎么办？

```bash
# 增加超时时间
npm install --timeout=60000

# 或使用代理
npm install --proxy=http://proxy.example.com:8080
```

---

## 📊 安装后的目录结构

```
monkey-brain-frontend/
├── node_modules/          # 依赖包（约 500MB）
│   ├── react/
│   ├── vite/
│   ├── antd/
│   └── ... 其他包
├── package.json           # 项目配置
├── package-lock.json      # 锁定依赖版本
└── ... 其他文件
```

---

## 🎯 安装完成后

### 启动开发服务器

```bash
npm run dev
```

访问：`http://localhost:5173`

### 构建生产版本

```bash
npm run build
```

构建文件在 `dist/` 目录

### 运行测试

```bash
npm run test
```

### 代码检查

```bash
npm run lint
```

---

## 💡 不同场景的安装方式

### 场景 1: 本地开发

```bash
cd monkey-brain-frontend
npm install
npm run dev
```

### 场景 2: 服务器部署（生产环境）

```bash
cd monkey-brain-frontend
npm ci --only=production
npm run build
```

### 场景 3: CI/CD 环境

```bash
cd monkey-brain-frontend
npm ci
npm run build
npm run test
```

### 场景 4: 离线安装

```bash
# 在有网络的机器上打包
npm pack
tar -czf node_modules.tar.gz node_modules/

# 在离线机器上
tar -xzf node_modules.tar.gz
```

---

## 📦 依赖包说明

### 主要依赖（生产环境需要）

- **react** - React 框架
- **react-dom** - React DOM 渲染
- **vite** - 构建工具
- **antd** - UI 组件库
- **axios** - HTTP 客户端
- **zustand** - 状态管理
- **@niivue/niivue** - 3D 可视化

### 开发依赖（仅开发时需要）

- **typescript** - TypeScript 支持
- **eslint** - 代码检查
- **vitest** - 测试框架
- **tailwindcss** - CSS 框架

---

## 🔍 验证安装

### 检查关键包是否安装

```bash
# 检查 React
npm list react

# 检查 Vite
npm list vite

# 检查 Ant Design
npm list antd

# 检查所有包
npm list --depth=0
```

### 测试运行

```bash
# 启动开发服务器
npm run dev

# 如果能看到以下输出，说明安装成功：
# VITE v5.x.x  ready in xxx ms
# ➜  Local:   http://localhost:5173/
```

---

## 🎉 安装完成！

现在你可以：

1. **开发**: `npm run dev`
2. **构建**: `npm run build`
3. **测试**: `npm run test`
4. **检查**: `npm run lint`

如果遇到问题，请查看：
- `README.md` - 项目说明
- `package.json` - 查看所有可用命令
- 或运行 `npm run` 查看所有脚本

---

## 📞 需要帮助？

- 查看 `README.md` 了解项目详情
- 查看 `QUICK_START_SINGULARITY.md` 了解容器部署
- 查看 `package.json` 中的 `scripts` 部分了解所有命令
