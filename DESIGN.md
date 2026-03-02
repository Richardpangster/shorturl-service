# ShortURL Service - 设计文档

## 项目概述

一个完整的 URL 短链服务，包含 REST API 和简单的前端页面。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | Python 异步框架，自动生成 API 文档 |
| 数据库 | SQLite | 轻量级，无需额外服务 |
| 缓存 | Redis | 缓存短码映射，加速跳转 |
| 前端 | Jinja2 + Vanilla JS | 简单 HTML 表单，无需构建 |
| 部署 | Docker Compose | 一键启动所有服务 |

## 系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI    │────▶│   SQLite    │
│  (Browser)  │◀────│   Server    │◀────│  (主存储)   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │  (缓存层)   │
                    └─────────────┘
```

## API 设计

### 1. 创建短链
```
POST /api/shorten
Content-Type: application/json

Request:
{
  "url": "https://example.com/very/long/url",
  "expire_days": 30  // 可选，默认30天
}

Response (201):
{
  "short_code": "abc123",
  "short_url": "http://localhost:8000/abc123",
  "original_url": "https://example.com/very/long/url",
  "expires_at": "2026-04-01T12:00:00"
}
```

### 2. 跳转（核心功能）
```
GET /{short_code}

Response: 302 Redirect to original_url
```

### 3. 查看统计
```
GET /api/stats/{short_code}

Response:
{
  "short_code": "abc123",
  "original_url": "https://example.com/...",
  "created_at": "2026-03-01T12:00:00",
  "expires_at": "2026-04-01T12:00:00",
  "visit_count": 42,
  "last_visited_at": "2026-03-02T08:30:00"
}
```

### 4. 前端页面
```
GET /
返回 HTML 表单页面，包含：
- 输入框：输入长链接
- 按钮：生成短链
- 结果展示：显示生成的短链和二维码
```

## 数据模型

### SQLite 表结构

```sql
-- urls 表
CREATE TABLE urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    short_code VARCHAR(6) UNIQUE NOT NULL,
    original_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    visit_count INTEGER DEFAULT 0,
    last_visited_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_short_code ON urls(short_code);
CREATE INDEX idx_expires_at ON urls(expires_at);
```

## 短码生成算法

1. 使用 `secrets.token_urlsafe(4)` 生成 6 位短码（Base64 URL safe）
2. 检查是否重复，重复则重新生成
3. 备选方案：自增 ID + Base62 编码

## 项目结构

```
shorturl-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 入口
│   ├── config.py         # 配置管理
│   ├── models.py         # SQLAlchemy 模型
│   ├── database.py       # 数据库连接
│   ├── cache.py          # Redis 缓存封装
│   ├── services.py       # 业务逻辑
│   └── routers/
│       ├── __init__.py
│       ├── redirect.py   # 跳转路由
│       ├── api.py        # API 路由
│       └── pages.py      # 前端页面路由
├── static/
│   └── style.css         # 简单样式
├── templates/
│   └── index.html        # 前端页面
├── tests/
│   └── test_api.py       # API 测试
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── DESIGN.md             # 本文件
```

## 配置项

```python
# 环境变量或配置文件
DATABASE_URL = "sqlite:///./shorturl.db"
REDIS_URL = "redis://localhost:6379/0"
BASE_URL = "http://localhost:8000"  # 短链前缀
DEFAULT_EXPIRE_DAYS = 30
SHORT_CODE_LENGTH = 6
```

## 任务分解

### Task 1: 基础框架搭建
- [ ] 创建 FastAPI 项目结构
- [ ] 配置 SQLAlchemy + SQLite
- [ ] 配置 Redis 连接
- [ ] 创建数据模型

### Task 2: 核心 API 开发
- [ ] 实现短码生成算法
- [ ] 实现 POST /api/shorten
- [ ] 实现 GET /{short_code}（跳转）
- [ ] 实现 GET /api/stats/{short_code}

### Task 3: 前端页面
- [ ] 创建 HTML 模板
- [ ] 实现表单提交（AJAX）
- [ ] 美化样式

### Task 4: 测试与部署
- [ ] 编写 API 测试
- [ ] 创建 Dockerfile
- [ ] 创建 docker-compose.yml
- [ ] README 文档

## 验收标准

- [ ] API 文档自动生成（/docs）
- [ ] 跳转响应时间 < 50ms（Redis 缓存命中）
- [ ] 过期短链自动清理
- [ ] 前端页面可用，交互流畅
- [ ] Docker Compose 一键启动
- [ ] 测试覆盖率 > 80%

