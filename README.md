# EduToyProject · 研迹

**面向研究生的 AI 协作科研成长支持系统。**

研迹围绕研究问题，将科研记录、尝试结果、个人判断、成长证据和下一步计划连接起来，帮助研究生回答：**我在探索什么、我贡献了什么、我学到了什么、接下来准备做什么。**

这是“软件工程实践”课程的 5 人团队项目。“研迹”为暂定产品名称，仓库名称保留为 `EduToyProject`。

> 当前已实现 **M1：科研记录闭环与独立账号**，使用本地 SQLite 文件，无需 Docker。研究地图、AI 整理、贡献成长和行动规划属于后续里程碑。提交与远端同步状态见[开发进度](docs/DEVELOPMENT_PROGRESS.md)。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [项目说明](docs/PROJECT_OVERVIEW.md) | 产品定位、全部功能规格、当前与后续范围、课程交付 |
| [全局架构与数据流](docs/ARCHITECTURE.md) | 模块边界、对象关系、API、归属、事务、版本和未来模块约定 |
| [开发进度记录](docs/DEVELOPMENT_PROGRESS.md) | 里程碑、任务、实际验证结果、决策变化与待办 |

## 当前可以做什么

- 注册、登录、退出；同一后端的不同账号拥有独立的项目和记录。
- 创建、修改、归档和恢复研究项目；未建项目也可以保存随手记。
- 新建随手记、论文阅读、实验尝试、AI 协作或灵感疑问，编辑背景、行动、观察、判断和后续想法。
- 导入 `.md` / `.txt`，预览后保存；支持 UTF-8/BOM，单文件最大 1 MiB。
- 查看与修订原始材料、添加参考链接、回看记录历史与来源版本。
- 按中文关键词、项目、类型、工作状态和结果判断筛选，分页浏览，删除与恢复记录。
- 保存失败保留输入；会话过期可原地重新登录；并发编辑提示冲突。
- 刷新或重启后继续使用；通过命令备份数据库。

四个主导航均保留，其中“科研记录”已开放，另外三页明确显示开发状态。当前不调用模型，不抓取链接，不提供团队共享、云端同步、PDF 解析、密码找回、历史回滚或永久删除。

## 本地安装与启动

已验证环境：**Python 3.12、Node.js 24、npm**。以下命令使用 macOS/Linux shell，从仓库根目录执行。

```bash
git clone https://github.com/Brwaey/EduToyProject.git
cd EduToyProject
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

如果本机 `python3` 已是 3.12，可用它代替 `python3.12`。Windows 的虚拟环境入口位于 `backend\.venv\Scripts\python.exe`，其余配置相同。

在第一个终端启动后端：

```bash
backend/.venv/bin/python backend/run.py
```

在第二个终端启动前端：

```bash
npm --prefix frontend run dev -- --strictPort
```

打开 **<http://127.0.0.1:5173>**，创建自己的账号。后端默认位于 `127.0.0.1:8000`。首次启动会自动创建目录和 SQLite 数据库、执行 Alembic 迁移；后续启动保留数据并应用新迁移。迁移失败会停止启动并报告原因。

- [API 文档](http://127.0.0.1:8000/docs)
- [存活检查](http://127.0.0.1:8000/api/v1/health/live)
- [数据库及迁移就绪检查](http://127.0.0.1:8000/api/v1/health/ready)

不需要手动建表。后端为单个服务进程；数据库忙时最多等待 5 秒，超时提示重试。用 `Ctrl+C` 停止服务。

### 可选配置

默认配置可以直接启动。需要修改时，将 `.env.example` 复制为仓库根目录的 `.env`：

| 变量 | 默认值 / 用途 |
| --- | --- |
| `EDUTOY_DB_PATH` | `data/edutoy.sqlite3`；可用绝对路径，相对路径始终从仓库根目录解析 |
| `EDUTOY_HOST` / `EDUTOY_PORT` | `127.0.0.1` / `8000`，后端监听地址 |
| `EDUTOY_ORIGINS` | 本地 5173 / 4173 的 localhost 与 127.0.0.1 来源，逗号分隔 |
| `EDUTOY_SECURE_COOKIE` | `false`；HTTPS 部署时设置为 `true` |

前端 `/api` 请求由 Vite 代理到后端。若修改后端端口，启动 Vite 时同时指定目标，例如：

```bash
EDUTOY_API_TARGET=http://127.0.0.1:8002 npm --prefix frontend run dev -- --strictPort
```

修改前端地址或端口时也要更新后端 `EDUTOY_ORIGINS`。默认仅供本机运行；生产托管与公网部署属于后续交付工作。

## 数据位置与备份恢复

默认数据文件为 **`data/edutoy.sqlite3`**，包含账号、会话、项目、记录、来源及历史。每台电脑独立运行时拥有自己的文件；GitHub 只同步代码和文档。数据库、备份、环境文件和密钥均被 Git 忽略。

创建一致性备份（可在服务运行时使用；目标文件必须尚不存在）：

```bash
backend/.venv/bin/python backend/scripts/backup.py backups/yanji-2026-10-02.sqlite3
```

恢复步骤：

1. 停止后端，确认没有其他进程访问当前数据库。
2. 先用上述命令备份当前数据库到另一个新文件。
3. 将待恢复备份复制到 `EDUTOY_DB_PATH` 指向的位置，默认示例：`cp backups/yanji-2026-10-02.sqlite3 data/edutoy.sqlite3`。
4. 按原命令启动后端，检查就绪接口及账号内记录。

备份包含完整的私有材料和账号数据，请保存在合适的位置。本轮仅使用 SQLite 默认 DELETE 日志模式。

## 开发检查

后端（在 `backend/` 内执行）：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check app scripts tests migrations run.py
.venv/bin/ruff format --check app scripts tests migrations run.py
```

前端（在 `frontend/` 内执行）：

```bash
npm run generate:api
npm run typecheck
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
```

后端测试使用临时 SQLite 文件，经过与应用相同的迁移和连接配置。Playwright 自动启动测试专用后端 `8001` 和前端 `5174`，每轮新建临时数据库，覆盖桌面和手机尺寸；不读取或重置日常数据。请确保测试端口空闲。

API 以 FastAPI OpenAPI 为准。修改接口后运行 `generate:api`，同步 `backend/openapi.json` 与 `frontend/src/api.generated.ts`。Python 依赖约束位于 `requirements.in`，锁定安装结果位于 `requirements.txt`；npm 使用 `package-lock.json`。

修改数据模型后，从仓库根目录生成迁移，并审查生成的批处理和数据保留逻辑：

```bash
backend/.venv/bin/alembic -c backend/alembic.ini revision --autogenerate -m "describe_change"
```

提交迁移文件，更新就绪检查要求的结构版本，并在临时数据库上验证全新升级和旧版本升级。当前模型与迁移是否一致可用 `backend/.venv/bin/alembic -c backend/alembic.ini check` 检查。

## 仓库结构

```text
EduToyProject/
├── README.md
├── .env.example
├── docs/                    # 产品说明、全局架构、开发进度
├── backend/
│   ├── app/                 # API、认证、模型、事务服务与配置
│   ├── migrations/          # Alembic 表结构版本
│   ├── scripts/             # 备份与 OpenAPI 导出
│   ├── tests/               # 数据库/API 集成测试
│   ├── openapi.json
│   ├── requirements.txt
│   └── run.py               # 迁移并启动服务
├── frontend/
│   ├── src/                 # 中文页面、查询缓存与 API 类型
│   ├── e2e/                 # Playwright 关键流程测试
│   └── package.json
└── data/                    # 首次运行生成，不进入 Git
```

## 后续目标与协作

产品以自我调节学习中的目标设定、执行监控、反思和调整为设计主线。改善掌控感是预期价值，实际效果尚未验证。后续按 **M2 研究地图与行动 → M3 AI 辅助整理 → M4 贡献成长 → M5 整体验收与发布**推进，完整规格保留在项目说明中。

- 开发前查看产品说明、架构与进度，按功能编号拆分任务。
- 功能变更同步数据流、API、测试与文档；经过实际验证后才标记完成。
- 原始材料、用户判断和 AI 建议分别保存，AI 建议经用户确认后才能写入正式对象。
- 公开演示使用虚构或脱敏材料；真实科研数据和 API 密钥不进入仓库。

课程参考：[课程仓库](https://github.com/bettermorn/IntelligentSWEPractice) · [课程 Wiki](https://github.com/bettermorn/IntelligentSWEPractice/wiki)。产品方案属于本团队设计，课程要求以教师发布材料为准。
