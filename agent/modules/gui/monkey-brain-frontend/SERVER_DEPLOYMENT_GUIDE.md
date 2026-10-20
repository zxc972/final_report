# 🧠 猴脑分割系统 - 服务器部署指南

## 📋 概述
将猴脑分割前端系统部署到 Linux 服务器。

## 🚀 快速启动

### 方法一：直接启动（推荐）
```bash
cd monkey-brain-frontend
./start-notebook.sh
```

### 方法二：使用 npm 命令
```bash
cd monkey-brain-frontend
npm run dev
```

## 🌐 访问方式

### 1. SSH 端口转发（推荐）
```bash
# 在本地机器上执行
ssh -L 5173:localhost:5173 username@server_ip

# 然后在本地浏览器访问
http://localhost:5173
```

### 2. 直接访问服务器 IP
```bash
http://服务器IP:5173
```

## ⚙️ 服务器配置

### 防火墙设置
```bash
# Ubuntu/Debian
sudo ufw allow 5173

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=5173/tcp
sudo firewall-cmd --reload
```

## 🔧 故障排除

### 端口被占用
```bash
# 查看端口占用
lsof -i :5173

# 杀死占用进程
kill -9 <PID>
```

### 权限问题
```bash
chmod +x start-notebook.sh
```

---

查看更多部署选项：`QUICK_START_SINGULARITY.md`
