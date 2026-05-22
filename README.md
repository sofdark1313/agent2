# 自动推文助手

本项目是一个本地 Web 控制台，用于把 Markdown 或主题需求转换成微信公众号文章，并通过微信公众号官方 API 创建草稿、可选自动发布。

## 技术栈

- Backend: Python FastAPI, SQLAlchemy 2.x, Alembic, MySQL
- Frontend: Vue 3, Vite, TypeScript
- AI: OpenAI-compatible Chat Completions API
- WeChat: 公众号 access token、图文图片上传、永久素材、草稿箱、发布接口

## 快速开始

1. 复制环境变量：

```powershell
Copy-Item .env.example .env
```

2. 启动 MySQL：

```powershell
docker compose up -d mysql
```

如果代码在 Windows、MySQL 在 Linux/WSL/Docker 中运行，请把 `.env` 里的 `MYSQL_DSN` 主机名改成 Windows 能访问到的 Linux 地址：

```env
MYSQL_DSN=mysql+pymysql://autopost:autopost@<linux-ip>:3306/autopost?charset=utf8mb4
```

同一台机器的 WSL2/Docker Desktop 通常可以先试 `localhost`；独立 Linux 虚拟机或服务器用它的局域网 IP。

AI 模型只需要配置三个参数，适配提供 OpenAI 兼容接口的国产模型：

```env
AI_BASE_URL=https://your-provider.example.com/v1
AI_API_KEY=your-api-key
AI_MODEL_NAME=your-model-name
```

例如 DeepSeek 常见配置形态：

```env
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-...
AI_MODEL_NAME=deepseek-chat
```

例如 Moonshot/Kimi 常见配置形态：

```env
AI_BASE_URL=https://api.moonshot.cn/v1
AI_API_KEY=sk-...
AI_MODEL_NAME=kimi-k2.6
```

启动后可以用下面接口测试 AI 是否真的可用：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/settings/ai/test
```

3. 安装后端依赖并迁移数据库：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

4. 安装前端依赖并启动：

```powershell
cd frontend
npm install
npm run dev
```

前端默认访问 `http://localhost:5173`，后端默认访问 `http://localhost:8000`。

## 微信发布前提

第一版只走微信公众号官方 API，不做网页后台模拟登录。真实创建草稿/发布需要公众号具备相应接口权限，并配置：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- 公众平台 IP 白名单
- 素材、草稿箱、发布相关能力

如果微信配置缺失，系统仍可生成和预览文章，但发布预检会返回明确原因。

## 参考文档

- WeChat access token: https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html
- WeChat draft add: https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
- WeChat publish: https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html
- OpenAI-compatible Chat Completions API: https://platform.openai.com/docs/api-reference/chat
