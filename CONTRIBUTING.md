# ZRAG 贡献指南

ZRAG 是一个本地优先的个人 RAG 知识库问答系统，代码以 MIT 许可证开源。欢迎通过缺陷报告、文档改进和代码提交参与项目。本文档说明接受哪些类型的贡献、如何搭建开发环境、分支与提交的约定、测试命令、代码规范入口以及 Pull Request 的检查流程。

需要先说明项目的协作背景：ZRAG 由个人主导维护，没有专职的评审团队，也没有固定的发版节奏。因此，小型改动（修正文档、补充测试、修复明确的缺陷）可以直接提交；涉及模块边界、存储结构、API 契约或依赖变更的大型改动，建议先开 issue 讨论方向，避免在错误的方向上投入大量工作后再被退回。

---

# 目录

[1. 欢迎与适用范围](#1-欢迎与适用范围)

[2. 开发环境](#2-开发环境)

[3. 分支与提交模型](#3-分支与提交模型)

[4. 测试](#4-测试)

[5. 代码规范](#5-代码规范)

[6. 文档](#6-文档)

[7. Pull Request 检查清单](#7-pull-request-检查清单)

---

# 1. 欢迎与适用范围

本项目接受的贡献分为三类。第一类是**缺陷报告**，包括功能异常、部署失败、文档描述与实现不符等；这类贡献不需要你修改代码，但需要提供可复现的信息，仓库的 `.github/ISSUE_TEMPLATE/bug_report.md` 已经列出了应当填写的字段，包括复现步骤、期望行为、实际行为、环境信息与脱敏后的日志。第二类是**文档改进**，包括修正错别字、补充示例、更新已经滞后的设计说明；文档是本项目的重要资产，`docs/` 下的设计文档与代码同步演进，发现不一致时欢迎指出。第三类是**代码**，包括新功能、缺陷修复、重构与测试补充。

对于代码贡献，需要区分改动规模。小范围、边界清晰的修改（例如为某个工具函数补充边界值测试、修正一处异常处理、更新一处配置说明）可以直接提交 PR。涉及以下任一情况的改动，建议先开 issue 说明动机、方案与影响面，再开始实现：新增或修改 `config/` 下的配置项、变更 API 路径或请求/响应结构、调整数据库表结构或 ChromaDB 中的集合布局、引入新的第三方依赖、修改摄入管道或检索融合策略、改变前端路由与构建方式。这样做的目的是让维护者在早期判断改动是否符合项目定位，而不是等到 PR 完成后才发现方向不一致。

也请理解项目的范围边界。`docs/PRD.md` 的「不在范围内」一节明确列出了当前阶段不处理的能力，例如多用户隔离、基于消息队列的异步摄入、分布式向量检索集群。与这些方向相关的改动并非永远不被接受，但需要先通过 issue 讨论，确认是否属于当前阶段的目标。

---

# 2. 开发环境

ZRAG 由 Python 后端与 Vue 前端组成，二者可以分别在本机运行，也可以通过 Docker Compose 一起部署。开发环境需要的版本与容器构建、CI 配置保持一致：后端使用 **Python 3.10**（`Dockerfile.backend` 的基础镜像为 `python:3.10-slim`，CI 也使用 3.10），前端使用 **Node 22**（`Dockerfile.frontend` 使用 `node:22-alpine`，CI 使用 22），容器化部署需要 **Docker Engine >= 24.0**（见 `README.md` 的部署前提条件）。

后端的本地开发流程与 `README.md` 中给出的一致。先创建独立虚拟环境，这是项目规范的要求，避免污染系统 Python；随后安装 `requirements.txt` 中的依赖，并设置 API Key。完整的命令如下：

```bash
# 1. 创建虚拟环境
python3.10 -m venv .venv
source .venv/bin/activate

# 2. 安装运行时依赖
pip install -r requirements.txt

# 3. 设置 API Key
export ZRAG_API_KEY=your-key
export LITELLM_MASTER_KEY=your-key

# 4. 初始化数据库并启动开发服务器
python manage.py migrate
python manage.py runserver 0.0.0.0:5965
```

如果你需要运行测试，还需要额外安装 `pytest` 与 `pytest-django`。这两个包不在 `requirements.txt` 中，因为它们是开发工具而非运行时依赖；CI 也是在安装完运行时依赖后再单独安装它们。`pytest-django` 会读取 `pytest.ini` 中的 `DJANGO_SETTINGS_MODULE = zrag.settings` 并完成 Django 初始化，因此不要在测试命令中覆盖该设置。

前端的开发流程是在 `frontend/` 目录中安装依赖并启动 Vite 开发服务器。开发服务器默认监听 `http://localhost:5173`，并自动把 API 请求代理到后端的 `:5965`，因此本地无需额外配置跨域。命令如下：

```bash
cd frontend
npm install
npm run dev
```

如果涉及摄入功能的联调，需要准备 Embedding 模型。模型不随仓库分发，`README.md` 给出了下载命令，将模型缓存到项目根目录的 `./models`；本地运行时把 `MODELS_DIR` 指向该目录，容器部署时则由 `MODELS_DIR_HOST` 挂载到容器内的 `/app/models`：

```bash
python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"
```

容器化部署时，先复制环境变量模板并填入实际值，再构建启动。注意 `.env` 不应提交到仓库，`ZRAG_API_KEY` 与 `LITELLM_MASTER_KEY` 必须自行生成，不能沿用模板中的占位值：

```bash
cp .env.example .env
# 编辑 .env 填入 ZRAG_API_KEY、LITELLM_MASTER_KEY 等
docker compose up -d --build
```

---

# 3. 分支与提交模型

本项目采用**主线开发、主线上线**的模式：不强制使用 feature 分支，也不维护 `develop`、`release` 等长期分支。改动直接提交到 `main`，`main` 的最新提交就是当前的可用版本。这种模式适合个人主导、发布节奏不固定的小型项目，可以省去分支合并与版本回补的额外开销；代价是对提交质量的要求更高，因此提交前的测试与自查不能省略。

如果你不希望直接推送到 `main`，也可以自建分支后提交 Pull Request。CI 配置在 `pull_request` 事件上会运行后端与前端测试，因此 PR 方式同样可用。无论采用哪种方式，提交信息都应使用约定式前缀，便于从 `git log` 中快速识别改动类型。前缀与含义如下：

| 前缀 | 含义 | 典型场景 |
|------|------|---------|
| `feat:` | 新增功能 | 新增 API、检索策略、前端页面或配置能力 |
| `fix:` | 缺陷修复 | 修复异常行为、边界错误、错误的配置读取 |
| `docs:` | 文档 | 更新 `README.md`、`docs/` 下的设计文档或注释性说明 |
| `refactor:` | 重构 | 不改变外部行为的结构调整、拆分模块、消除重复 |
| `test:` | 测试 | 新增或修正测试用例、测试工具与夹具 |
| `chore:` | 杂项 | 依赖升级、构建脚本、CI 配置、忽略规则等维护性改动 |

提交信息应说明「为什么改」而不只是「改了什么」。例如 `fix:` 后面应当点明修复的具体问题（如「修正摄入任务在空文档时的状态卡死」），而不是笼统写「修复 bug」。如果一次提交同时包含功能与重构，建议拆成多个提交，使每个提交都能独立解释。仓库的提交历史可以在同一提交内合并多个相关文件，但不要在一次提交中混入无关的格式化改动，否则评审时很难区分真正的行为变化。

---

# 4. 测试

提交前必须保证测试通过。项目规范明确要求不允许提交测试未通过的代码，CI 也会在推送 `main` 或创建 PR 时执行测试。后端与前端使用不同的测试框架，命令分别来自 `README.md`、`pytest.ini` 与 `frontend/package.json` 的实际配置。

后端使用 pytest。在仓库根目录执行：

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

`pytest.ini` 只设置了 `DJANGO_SETTINGS_MODULE = zrag.settings`，没有额外的插件或路径配置，因此上述命令即可完成 Django 初始化并收集 `tests/` 下的用例。需要注意，`tests/test_08_bge_embedder.py` 会实际加载 `BAAI/bge-small-zh-v1.5` 模型，而 CI 环境没有模型缓存，因此 `.github/workflows/ci.yml` 在 CI 中通过 `--ignore=tests/test_08_bge_embedder.py` 排除了该文件。在本地已经下载模型的情况下，可以完整运行；如果没有模型，请在提交说明中注明哪些测试被跳过以及原因。

前端使用 Vitest。命令在 `frontend/` 目录执行：

```bash
cd frontend
npm run test
```

`package.json` 中 `test` 脚本的实际命令为 `vitest run`，执行一次后退出，适合提交前与 CI 使用。开发过程中可以使用 `npm run test:watch`（对应 `vitest`）进行监听模式迭代，但提交前应以一次性的 `npm run test` 结果为准。若改动涉及前端构建配置或依赖，建议同时执行 `npm run build`，确认生产构建可以通过。

CI 的触发条件与执行内容可以在 `.github/workflows/ci.yml` 中查看：后端 job 在 Python 3.10 下安装运行时依赖与测试工具后执行 pytest，前端 job 在 Node 22 下执行 `npm ci`、`npm run test` 与 `npm run build`。本地测试与 CI 使用相同的命令，可以提前发现问题，减少往返。

---

# 5. 代码规范

代码规范集中存放在 `.claude/rules/` 目录中，这些规范同时适用于人工贡献与 AI 辅助贡献。把规范放在独立文件中，而不是复制进本文档，是为了避免两处内容不同步：当规范更新时，只需要修改对应文件，本文档保持为导航入口。开始编码前，请至少阅读与你改动相关的规范文件。

| 规范文件 | 适用范围 | 主要内容 |
|---------|---------|---------|
| [.claude/rules/python-code-style.md](.claude/rules/python-code-style.md) | 后端 Python 代码 | 方法与类注释、目录结构、异常与日志、OOP 设计取舍、if/else 重构 |
| [.claude/rules/nodejs-code-style.md](.claude/rules/nodejs-code-style.md) | 前端 Vue/TypeScript 代码 | JSDoc、目录结构、Vue 3 SFC 与 composable 设计、Vitest 测试规范 |
| [.claude/rules/python.md](.claude/rules/python.md) | Python 依赖与环境 | 第三方依赖记录、虚拟环境管理 |
| [.claude/rules/container.md](.claude/rules/container.md) | 容器与镜像 | 多阶段构建、镜像 tag 约定、容器资源与清理 |
| [.claude/rules/debug.md](.claude/rules/debug.md) | 调试与联调 | 日志跟踪、问题复现与定位流程 |
| [.claude/rules/scm.md](.claude/rules/scm.md) | 版本管理 | CalVer / SemVer / 构建标识的版本号体系 |

这些规范的详略程度不同：`python-code-style.md` 与 `nodejs-code-style.md` 给出了注释格式、函数长度、嵌套层数、日志字段等具体约束，属于提交前应当对照的硬性规范；`python.md` 与 `container.md` 更偏向环境与构建约定；`debug.md` 与 `scm.md` 则描述流程与版本策略。项目根目录的 `CLAUDE.md` 汇总了这些规范的入口，并额外说明了文档编写、数据库写操作与主会话协作等规则，可以作为总览。

如果规范与当前代码存在冲突，请先判断是哪一方滞后。规范更新但代码未跟进时，不建议在无关的 PR 中顺手全局重写，而应在对应模块的改动中逐步收敛；如果规范本身已经不适合当前实现，可以在 issue 中提出调整建议。运行 `pytest` 与 `npm run test` 是底线要求，规范中的注释与结构约定则依赖提交者自觉遵守，评审时会重点检查。

---

# 6. 文档

文档是 ZRAG 的一部分，而不是代码的附属说明。`docs/` 目录由 `docs/README.md` 作为唯一入口，其中按读者角色（使用者、贡献者、维护者与研究者）组织了文档地图，并在第 5 节「文档维护约定」中给出了四条规则。贡献文档时请遵循这些既有约定，而不是另起一套结构。

最重要的一条是：**任何在 `docs/` 下新增的 Markdown 文件，必须在 `docs/README.md` 的文档地图与各文档简介中登记**，说明其用途、适合的读者以及与上下游文档的关系。未登记的文档会成为孤立文档，只能靠全文搜索发现，违背索引作为唯一入口的初衷。删除或重命名文档时，也要同步清理索引与其他文档中的引用。项目根目录下的 `README.md`、`SECURITY.md`、`CONTRIBUTING.md` 属于仓库级文件，不属于 `docs/` 索引的登记范围。

第二条是：**文档内的相对链接必须指向真实存在的文件**。GitHub 对失效链接不会报错，只会静默跳转到 404，因此这类问题往往到读者点击时才被发现。提交前请用 `ls` 或 `test -f` 逐一验证相对路径，尤其是跨目录引用（例如从 `docs/README.md` 引用根目录的 `README.md` 时使用 `../README.md`）。同时，文档中的命令、版本号与环境变量应与实际配置文件一致；本文档与 `SECURITY.md` 中的命令均取自 `README.md`、`pytest.ini`、`frontend/package.json` 与 `.github/workflows/ci.yml`，可以作为核对基准。

此外，`design.md` 被索引声明为权威来源，模块级改动后应同步更新对应章节；`QA/` 是历史对话存档，原则上不回改，当结论被推翻时由 `design.md` 覆盖即可。如果你的改动涉及新增配置项或环境变量，请同时更新 `README.md` 的配置清单与 `.env.example`，避免使用者按旧文档配置后无法启动。

---

# 7. Pull Request 检查清单

提交 Pull Request 前，请逐项核对以下检查项。仓库的 `.github/pull_request_template.md` 已经提供了结构相近的模板，包括变更说明、关联 issue、变更类型、测试情况与检查清单；本节把检查项集中列出，并说明每一项的实际含义，避免只勾选而不验证。

- [ ] **后端测试通过**：在仓库根目录执行 `source .venv/bin/activate && python -m pytest tests/ -v`，结果无失败。如果因缺少 Embedding 模型而跳过了 `tests/test_08_bge_embedder.py`，请在 PR 描述中说明。
- [ ] **前端测试通过**：在 `frontend/` 目录执行 `npm run test`，结果无失败。若改动涉及构建配置，额外执行 `npm run build`。
- [ ] **文档已更新**：如果改动涉及新增配置项、环境变量、API 结构或模块行为，已同步更新 `README.md`、`.env.example` 或 `docs/` 下的对应文档。
- [ ] **新文档已在索引登记**：若在 `docs/` 下新增了 Markdown 文件，已在 `docs/README.md` 的文档地图与简介中增加条目。
- [ ] **文档链接有效**：改动中出现的相对链接均指向真实存在的文件，命令、版本号与实际配置一致。
- [ ] **无密钥提交**：未提交 `.env`、`.mcp.json` 或其他包含 `ZRAG_API_KEY`、`LITELLM_MASTER_KEY`、`DJANGO_SECRET_KEY` 的本地配置文件。注意 `.gitignore` 已排除 `.env` 与 `.env.*`，但仍需自查是否误加了被强制追踪的文件。
- [ ] **无个人绝对路径**：代码、配置与文档中不包含 `/Users/你的用户名/...` 这类个人路径，统一使用相对路径或 `/path/to/...` 占位符。
- [ ] **无运行时数据**：未提交 `data/`、`logs/` 目录下的内容，包括 SQLite 数据库、ChromaDB 文件与日志。这些目录已在 `.gitignore` 中排除。
- [ ] **提交信息符合约定**：使用 `feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`chore:` 前缀，并在正文中说明改动动机。
- [ ] **关联 issue**：在 PR 描述中使用 `Closes #123` 或 `Refs #123` 关联相关 issue；若确实无需关联（例如修正错别字），请说明原因。

检查清单的目的不是增加流程负担，而是把容易遗漏、事后又难以补救的事项前置。密钥与个人数据一旦进入提交历史，即使后续删除文件，仍可能通过历史记录被恢复；失效链接与滞后的文档虽然不阻塞构建，却会持续消耗读者的时间。请把清单当作提交前的自查，而不是形式化的勾选。
