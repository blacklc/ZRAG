# 第三方组件许可证

## 说明

本文档列出 ZRAG 直接使用的第三方组件及其许可证，供合规审查与再分发参考。ZRAG 自身源码采用 MIT 许可证（见仓库根目录 `LICENSE`），第三方组件仍归各自版权人所有，并继续适用其原有许可证条款。

各组件版本取自仓库内的依赖声明文件：Python 运行时依赖来自 `requirements.txt`，前端直接依赖来自 `frontend/package.json` 及其锁定文件 `frontend/package-lock.json`，基础镜像来自 `Dockerfile.backend` 与 `Dockerfile.frontend`。许可证标识优先取自依赖声明文件中记录的字段；声明文件未记录时，取自本地虚拟环境 `.venv` 中已安装包的 `*.dist-info/METADATA` 元数据（`License-Expression`、`License` 或 `License :: OSI Approved` 分类器）。凡是无法由本地文件确定的条目，均在表中标注「需核实」并说明推测依据，不做无依据的断言。

需要特别注意的是：本项目通过 Docker 镜像分发，且前端构建产物会把若干前端依赖的代码内联进静态资源，因此再分发时（尤其是发布镜像或 `dist/` 产物时）应保留相应组件的版权声明与许可证文本。下文中 uWSGI 的 GPLv2 义务、以及 Embedding 模型的许可证问题，属于发布前必须确认的两项重点。

## 运行时依赖（Python）

以下依赖来自项目根目录的 `requirements.txt`，由 `Dockerfile.backend` 在构建阶段通过 `pip install -r requirements.txt` 安装，并随后端镜像一起分发。除 uWSGI 外，其余组件均为宽松许可证（MIT / BSD / Apache-2.0），义务集中于保留版权声明与许可证文本。

| 组件 | 版本 | 许可证 | 项目地址 |
|------|------|--------|----------|
| Django | 5.2.14（传递依赖，见下注） | BSD-3-Clause | https://www.djangoproject.com/ |
| djangorestframework | 3.17.1 | BSD-3-Clause | https://www.django-rest-framework.org/ |
| django-cors-headers | 4.9.0 | MIT | https://github.com/adamchainz/django-cors-headers |
| drf-spectacular | 0.28.0 | BSD-3-Clause | https://github.com/tfranzel/drf-spectacular |
| chromadb | 1.5.9 | Apache-2.0 | https://github.com/chroma-core/chroma |
| sentence-transformers | 5.5.1 | Apache-2.0 | https://github.com/huggingface/sentence-transformers |
| openai | 2.40.0 | Apache-2.0 | https://github.com/openai/openai-python |
| PyYAML | 6.0.3 | MIT | https://pyyaml.org/ |
| jieba | 0.42.1（已在 `requirements.txt` 中锁定，见下注） | MIT | https://github.com/fxsjy/jieba |
| uwsgi | 2.0.31 | GPL-2.0-only + linking exception（需核实精确 SPDX 组合，见「特殊说明：uwsgi」） | https://github.com/unbit/uwsgi |

补充说明：

- **Django** 未在 `requirements.txt` 中显式声明，但项目直接依赖它；本地虚拟环境 `.venv` 中实际安装版本为 5.2.14（由 djangorestframework 传递安装）。建议在 `requirements.txt` 中显式固定 Django 版本，以免不同环境解析出不同主版本。
- **jieba** 的 0.42.1 已依据已构建的后端镜像 `zrag-backend:latest` 中的实际安装确认（`jieba/__init__.py` 的 `__version__` 与 `jieba-0.42.1.dist-info/METADATA` 双重印证），并已在 `requirements.txt` 中固定为 `jieba==0.42.1`，因此构建产物不再随上游发版漂移。
- **drf-spectacular** 在 `requirements.txt` 中固定为 0.28.0，但本地 `.venv` 中实装的是 0.29.0（环境与声明文件不一致）。表中版本以声明文件为准；两者的许可证同为 BSD-3-Clause（依据已安装 0.29.0 的 `License-Expression: BSD-3-Clause` 元数据）。
- **chromadb** 与 **sentence-transformers** 的元数据未提供 `License-Expression` 字段，许可证取自其 `License :: OSI Approved :: Apache Software License` 分类器，分别为 Apache-2.0。
- **uwsgi** 未安装在本地虚拟环境中（仅在后端镜像的 builder 阶段编译安装），因此其许可证无法由本地文件核验，详细说明见文末专节。

## 前端依赖

前端依赖的整体情况比后端更复杂：`vue`、`vue-router`、`marked`、`highlight.js`、`dompurify` 会被 Vite 打包进 `dist/` 静态资源并随 `Dockerfile.frontend` 的运行时镜像分发，因此这些组件的版权声明与许可证文本需要随产物一并保留；其余开发依赖（构建工具、测试框架、样式处理工具）只存在于构建阶段，不会进入最终镜像，合规压力相对较小。下表的版本与许可证组合均读取自 `frontend/package-lock.json`（lockfileVersion 3）中对应 `node_modules/<包名>` 条目记录的 `version` 与 `license` 字段。

### 运行时依赖（打包进 dist 产物）

| 组件 | 版本 | 许可证 | 项目地址 |
|------|------|--------|----------|
| vue | 3.5.35 | MIT | https://github.com/vuejs/core |
| vue-router | 4.6.4 | MIT | https://github.com/vuejs/router |
| marked | 14.1.4 | MIT | https://github.com/markedjs/marked |
| highlight.js | 11.11.1 | BSD-3-Clause | https://github.com/highlightjs/highlight.js |
| dompurify | 3.4.7 | MPL-2.0 OR Apache-2.0（双许可，见下注） | https://github.com/cure53/DOMPurify |

补充说明：`dompurify` 在 lock 文件中记录的许可证表达式为 `MPL-2.0 OR Apache-2.0`，属于双许可，使用方可自行选择其一。若选择 Apache-2.0，则需保留版权与许可声明；若选择 MPL-2.0，还需注意 MPL 对文件级的宽松要求（修改其源文件后需以 MPL 公开该文件）。ZRAG 未修改 `dompurify` 源码，仅在打包时内联，因此两种选择下义务均以保留声明为主。

### 开发依赖（构建与测试阶段）

| 组件 | 版本 | 许可证 | 项目地址 |
|------|------|--------|----------|
| vite | 8.0.16 | MIT | https://github.com/vitejs/vite |
| @vitejs/plugin-vue | 6.0.7 | MIT | https://github.com/vitejs/vite-plugin-vue |
| vitest | 3.2.6 | MIT | https://github.com/vitest-dev/vitest |
| @vue/test-utils | 2.4.10 | MIT | https://github.com/vuejs/test-utils |
| happy-dom | 20.10.1 | MIT | https://github.com/capricorn86/happy-dom |
| tailwindcss | 3.4.19 | MIT | https://github.com/tailwindlabs/tailwindcss |
| postcss | 8.5.15 | MIT | https://github.com/postcss/postcss |
| autoprefixer | 10.5.0 | MIT | https://github.com/postcss/autoprefixer |

补充说明：`package.json` 中使用的是 `^` 版本范围，上表列出的是 `package-lock.json` 中实际解析并锁定的版本。CI 与镜像构建使用 `npm ci`（见 `Dockerfile.frontend`），因此构建产物与上表版本一致；若执行 `npm install` 刷新锁文件，版本可能发生变化，需同步更新本表。

## 基础镜像

镜像层面的合规问题与 Python/Node 包不同：基础镜像通常由「上游语言运行时」与「Linux 发行版用户空间」两部分组成，两者的许可证相互独立。`python:3.10-slim` 与 `node:22-alpine` 中的运行时分发许可证清晰；而 Alpine 与 Debian 用户空间包含大量系统包，各自适用不同许可证（GPL、LGPL、MIT、BSD 等混合），在对外分发镜像时通常通过保留发行版的许可证清单（如 `/usr/share/licenses`、`/usr/share/doc/*/copyright`）来满足义务。下表列出直接引用的基础镜像及其主要许可证归属。

| 镜像 | 许可证 | 说明 |
|------|--------|------|
| `python:3.10-slim` | Python 采用 PSF-2.0；镜像内 Debian 用户空间各包适用各自许可证 | `Dockerfile.backend` 的 builder 与 runtime 两个阶段均使用该镜像。builder 阶段额外安装 `gcc`、`libc6-dev`（Debian 包），runtime 阶段额外安装 `curl`；这些工具只用于编译或健康检查。最终镜像中不含 `gcc` 与 `libc6-dev`。 |
| `node:22-alpine` | Node.js 采用 MIT；Alpine 用户空间各包适用各自许可证 | 仅用于 `Dockerfile.frontend` 的 builder 阶段，不进入最终镜像。 |
| `nginx:alpine` | nginx 采用 BSD-2-Clause；Alpine 用户空间各包适用各自许可证 | `Dockerfile.frontend` 的 runtime 阶段基础镜像，最终前端镜像即基于它，内含构建后的 `dist/` 静态资源。 |

补充说明：`docker-compose.yml` 仅编排 `frontend` 与 `backend` 两个服务，均使用上述自建镜像，不直接引用额外第三方镜像；`nginx.conf` 所对应的反向代理 Nginx 为宿主机独立部署，不属于本项目分发物。若后续引入第三方数据库、缓存或网关镜像，应在本节补充相应条目。

## 机器学习模型

本项目涉及两类模型：一类是本地运行的 Embedding 模型，另一类是通过 LiteLLM Gateway 远程调用的生成模型。两者都不属于「源代码依赖」，其合规义务来自模型权重与模型卡所声明的许可证，而非代码仓库的许可证文件。

**Embedding 模型 `BAAI/bge-small-zh-v1.5`** 由 `config/embedding.yaml` 配置（`model_name: "BAAI/bge-small-zh-v1.5"`，输出 512 维向量），经 `sentence-transformers` 加载，本地推理设备为 `cpu`。

- **是否随仓库分发**：否。模型权重不在 Git 仓库中，也不在后端镜像内。`docker-compose.yml` 以只读卷将宿主机上的模型目录挂载到容器的 `/app/models`，`config/embedding.yaml` 的 `cache_dir` 默认指向 `/app/models`。README 中的下载命令会将权重复制到本地 `./models` 目录。
- **获取方式**：运行 `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"`，由 `sentence-transformers` 从 HuggingFace 拉取。
- **许可证**：**需核实** —— 以 HuggingFace 模型卡（https://huggingface.co/BAAI/bge-small-zh-v1.5）的 License 字段为准。本文档编写时无法联网核验该字段，故不在此断言具体许可证标识。发布前请打开模型卡确认；若模型卡标注为宽松许可证（如 MIT 或 Apache-2.0），则只需在再分发权重时保留模型卡与版权声明；若标注为需要署名或限制商用的条款，则应在 README 或本文件中明确提示使用者。
- **再分发影响**：由于仓库与镜像均不包含权重，ZRAG 的 MIT 许可证不会被模型许可证影响；只有当你自行分发包含权重的镜像或压缩包时，才需要把模型卡许可证文本一并附上。

**生成模型（LLM）** 由 `config/llm.yaml` 配置：`provider: "gateway"`，默认模型为网关别名 `smart-router`（Base URL 默认为 `http://localhost:4000/v1`，指向 LiteLLM Gateway），指代消解使用的小模型为 `qwen3:4b-instruct-2507-q4_K_M`（上下文窗口 32768 tokens）。

- **是否随仓库分发**：否。模型既不在仓库中，也不在镜像中，而是由外部的 LiteLLM Gateway 或本地 Ollama 等服务在运行时提供。ZRAG 仅通过 OpenAI 兼容接口调用它，不分发任何权重。
- **许可证**：**需核实** —— 各实际接入模型以其官方模型卡或上游发布页的许可证为准（`smart-router` 是网关侧的路由别名，其背后具体模型由网关配置决定，ZRAG 无法静态确定）。由于不分发权重，ZRAG 只需在文档中提示使用者自行遵守所接入模型的许可条款。
- **注意**：`config/llm.yaml` 中的 `api_key` 通过环境变量 `LITELLM_MASTER_KEY` 注入，仓库内不含任何真实密钥；对应的 `.env` 已被 `.gitignore` 与 `.dockerignore` 排除。

## 特殊说明：uwsgi

`uwsgi`（`requirements.txt` 中固定为 2.0.31）是后端镜像中唯一采用强著佐权（copyleft）许可证的组件，也是本项目许可证合规中最需要说明的一项。uWSGI 采用 **GPLv2 + linking exception**：基础许可为 GNU General Public License version 2，同时附有一项链接例外，允许以该例外条款许可的方式将 uWSGI 与其它代码组合使用，从而避免通过动态链接或进程加载把非 GPL 代码整体纳入 GPL 的传染范围。需要说明的是，精确的 SPDX 组合标识（例如是否写作 `GPL-2.0-only WITH <exception>`、以及例外条款的正式名称）应以 uWSGI 官方仓库中的 `LICENSE` 文件原文为准，本文标注为「需核实」，不在未核对原文的情况下给出确定标识。

关于对 ZRAG 自身源码的影响，结论如下：

1. **ZRAG 自身源码不因此被传染为 GPL。** 原因有两点：其一，uWSGI 作为独立进程运行，通过 `uwsgi.ini` 与 `entrypoint.sh` 以 WSGI 协议加载 Django 应用，属于进程间边界而非链接边界；其二，本项目未对 uWSGI 源码做任何修改，也未将其代码静态链接进 ZRAG 的 Python 模块。因此 `uwsgi` 的存在不改变 ZRAG 以 MIT 许可证发布的事实。
2. **但分发包含 uWSGI 的 Docker 镜像时，GPLv2 的义务会被触发。** GPLv2 要求向接收方提供对应的完整源代码（或提供有效的书面要约）。ZRAG 的后端镜像在 builder 阶段通过 `pip install uwsgi==2.0.31` 编译 uWSGI，并将其产物复制进 runtime 阶段，因此发布该镜像即构成对 uWSGI 二进制形式的分发。此时应在镜像文档、发布说明或本文件中给出获取对应源码的途径，并说明所使用的确切版本。
3. **源码获取地址：**
   - 官方仓库：https://github.com/unbit/uwsgi （对应 tag/commit 需与 2.0.31 版本对应）
   - 官方发布源（sdist）：https://pypi.org/project/uWSGI/2.0.31/#files
   - 若对 uWSGI 应用了任何补丁（当前项目未应用），必须一并提供补丁文件。

建议的合规做法是：在发布镜像的说明中写明「本镜像包含 uWSGI 2.0.31，其许可证为 GPLv2 + linking exception，源码可从上述地址获取」，并保留 uWSGI 的许可证原文。由于 uWSGI 未安装在本地虚拟环境中，本文无法从本地文件核验其许可证文本，故标注为需在发布前对照官方 `LICENSE` 文件复核。
