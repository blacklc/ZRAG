# Node.js 代码样式指南

本文章内容主要描述了针对于 Node.js/TypeScript 代码编写的样式风格指导。

## 方法注释

每一个 function/method 都需要添加 JSDoc 注释，需要简述当前方法的功能、所有形参的含义、异常抛出的细节以及返回结果的细节。

使用标准 JSDoc 格式，类型标注在花括号 `{ }` 中，参数名后跟连字符加描述。

- 示例1（普通函数）:
```typescript
/**
 * 计算分页偏移量
 *
 * @param {number} page - 当前页码，从 1 开始
 * @param {number} size - 每页条数
 * @returns {number} 计算后的偏移量
 */
function getOffset(page: number, size: number): number {
  return (page - 1) * size;
}
```

- 示例2（异步函数）:
```typescript
/**
 * 根据用户 ID 查询用户信息
 *
 * 优先从缓存中获取，缓存未命中时回源到数据库查询。
 * 查询结果会回写缓存，过期时间为 600 秒。
 *
 * @param {string} userId - 用户唯一标识
 * @param {Object} [options] - 查询选项
 * @param {boolean} [options.skipCache=false] - 是否跳过缓存
 * @throws {ValidationError} 当 userId 格式不合法时抛出
 * @throws {DatabaseError} 当数据库查询失败时抛出
 * @returns {Promise<User|null>} 用户信息对象，若用户不存在则返回 null
 */
async function getUserById(
  userId: string,
  options?: { skipCache?: boolean }
): Promise<User | null> {
  // ...
}
```

- 示例3（类方法）:
```typescript
class UserService {
  /**
   * 批量创建用户
   *
   * 该方法会校验每个用户的必填字段是否完整，
   * 校验通过后对密码进行哈希处理并持久化到数据库。
   *
   * @param {CreateUserDto[]} users - 待创建的用户列表
   * @param {string} operator - 操作人标识，用于记录创建者
   * @throws {ValidationError} 当用户列表中包含无效数据时抛出
   * @throws {DatabaseError} 当数据库写入失败时抛出
   * @returns {Promise<User[]>} 创建成功的用户列表（含生成的 ID）
   */
  async batchCreateUsers(
    users: CreateUserDto[],
    operator: string
  ): Promise<User[]> {
    // ...
  }
}
```

## 类注释

每一个自定义 class 都需要添加注释，需要说明当前类的用途以及其可能存在的业务含义。
对于 TypeScript，应优先使用 interface 或 type 来描述数据结构，class 仅在有实例方法或需要依赖注入时才使用。

- 示例1（服务类）:
```typescript
/**
 * 用户认证服务
 *
 * 负责用户的注册、登录、Token 签发与刷新等认证相关操作。
 * 依赖于 UserRepository 进行数据持久化，依赖于 JwtService 进行 Token 管理。
 * 使用依赖注入的方式接收上述依赖，便于单元测试时进行 mock。
 */
class AuthService {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly jwtService: JwtService
  ) {}

  // ...
}
```

- 示例2（中间件类）:
```typescript
/**
 * 请求日志中间件
 *
 * 使用 pino 作为日志记录器，记录每个 HTTP 请求的方法、URL、状态码及响应时间。
 * 通过继承基类 BaseMiddleware 获得标准的中间件生命周期管理能力。
 * 日志格式为 JSON，便于接入 ELK 等日志收集系统。
 */
class RequestLoggerMiddleware extends BaseMiddleware {
  // ...
}
```

- 示例3（抽象类）:
```typescript
/**
 * 缓存存储抽象基类
 *
 * 所有的缓存存储实现（如 RedisCache、MemoryCache、MemcachedCache）都必须继承该类。
 * 子类需要实现 get、set、delete 三个核心方法。
 * TTL 参数统一使用秒为单位，子类在实现时需自行转换为存储层的时间单位。
 */
abstract class CacheStore {
  abstract get<T>(key: string): Promise<T | null>;
  abstract set<T>(key: string, value: T, ttlSeconds: number): Promise<void>;
  abstract delete(key: string): Promise<boolean>;
}
```

## 代码目录结构

- 在构建代码结构目录时，应根据所需要完成的功能模块名称建立对应的模块目录。
- 尽可能保证项目的根目录下没有过多零散的代码文件。代码文件应该尽可能规整到相应的子目录内。
- 对于基础工具函数或类型定义，应存放于 `src/utils/` 和 `src/types/` 目录下。
- 对于与特定模块相关的代码，应存放在对应的模块子目录中（如 `src/modules/user/`、`src/modules/auth/`）。
- 测试相关的代码文件应存放于 `test/`、`__tests__/` 目录或与源文件同级的 `__tests__/` 目录中。
- 如果使用了开源框架（如 Express、NestJS、Next.js），应尽可能保证不改变原有框架推荐的目录结构。
- 相关的文档与图片应存放于项目根目录中的 `docs/` 目录中。这条规则不适用于 README.md，README.md 存放在项目的根目录中即可。
- 类型定义文件（`.d.ts`）应存放于 `src/types/` 或与实现文件同级的 `types/` 目录中。
- 项目所需的配置文件应存放于项目根目录中（如 `.env`、`.env.example`、`tsconfig.json`、`eslint.config.mjs` 等）。
- 项目相关的常量定义应存放于 `src/constants/` 目录下。
- `src/views/` 存放页面级 Vue 组件（对应路由的页面）。
- `src/components/` 存放可复用的通用组件，按功能域可建立子目录（如 `src/components/chat/`）。
- `src/composables/` 存放 Vue 3 组合式函数，每个 composable 聚焦单一领域概念。
- `src/router/` 存放 Vue Router 路由配置，路由定义与页面组件映射集中管理。
- `src/assets/` 存放图片、字体、全局样式等静态资源。
- 与特定页面强绑定的组件可放在对应 `views/` 子目录下，避免 `components/` 过度膨胀。
- 若项目有构建产出物，则这些产出物应存放于 `dist/` 或 `build/` 目录中，并确保通过 `.gitignore` 排除。

## Vue 3 项目特有规范

### SFC 结构顺序

Vue 单文件组件（SFC）应遵循 `template` → `script` → `style` 的结构顺序，各区块之间使用空行分隔。

```vue
<template>
  <div class="user-card">
    <h3>{{ user.name }}</h3>
    <p>{{ user.email }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { User } from '@/types/user'

const props = defineProps<{
  user: User
}>()

const displayName = computed(() => props.user.name || '未知用户')
</script>

<style scoped>
.user-card {
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}
</style>
```

### 优先使用 script setup 语法

新建组件时统一使用 `<script setup lang="ts">` 语法，避免使用 Options API 的 `export default defineComponent({ ... })` 写法。`script setup` 提供了更简洁的语法和更好的类型推断支持。

### 组件命名规范

- 组件文件名使用 PascalCase，例如 `SourceCard.vue`、`UserProfile.vue`。
- 在模板中引用组件时使用 kebab-case，例如 `<source-card />`、`<user-profile />`。
- 全局注册的组件应在 `main.ts` 或独立的注册文件中集中管理。

### Props 命名规范

在 `<script setup>` 中使用 `camelCase` 定义 props，在模板中引用时使用 `kebab-case`。每个 prop 必须明确指定 `type`、`required` 或 `default`，并添加 JSDoc 注释说明用途。

```vue
<script setup lang="ts">
/**
 * 用户信息卡片组件
 *
 * 展示用户头像、名称和简介信息，支持自定义尺寸和点击事件。
 * 当用户数据为空时显示占位内容。
 */
interface UserCardProps {
  /** 用户显示名称 */
  userName: string
  /** 用户邮箱地址 */
  email?: string
  /** 头像 URL 地址 */
  avatarUrl?: string
  /** 卡片尺寸 */
  size?: 'small' | 'medium' | 'large'
}

const props = withDefaults(defineProps<UserCardProps>(), {
  email: '',
  avatarUrl: '',
  size: 'medium'
})
</script>

<template>
  <div class="user-card" :class="`user-card--${size}`">
    <img :src="avatarUrl || '/default-avatar.png'" :alt="user-name" />
    <h3>{{ userName }}</h3>
    <p v-if="email">{{ email }}</p>
  </div>
</template>
```

### Emits 命名规范

emit 的函数名在 `<script setup>` 中使用 `camelCase`，在模板中使用 `kebab-case`。每个 emit 应通过 `defineEmits` 显式声明。

```vue
<script setup lang="ts">
const emit = defineEmits<{
  /** 用户点击卡片时触发，返回用户 ID */
  (e: 'card-click', userId: string): void
  /** 用户关闭卡片时触发 */
  (e: 'card-close'): void
}>()

function handleClick() {
  emit('card-click', props.userId)
}
</script>

<template>
  <div class="card" @click="handleClick">
    <button @click="$emit('card-close')">关闭</button>
  </div>
</template>
```

### 避免 v-if 与 v-for 同元素使用

`v-if` 和 `v-for` 不应同时作用于同一个元素。推荐使用计算属性预先过滤数据，或使用外层包裹元素分别处理。

```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { TodoItem } from '@/types/todo'

const props = defineProps<{
  todos: TodoItem[]
}>()

/** 过滤出未完成的待办事项 */
const activeTodos = computed(() => props.todos.filter(todo => !todo.completed))
</script>

<template>
  <!-- 正确做法：使用计算属性过滤 -->
  <ul>
    <li v-for="todo in activeTodos" :key="todo.id">
      {{ todo.title }}
    </li>
  </ul>

  <!-- 错误做法：v-if 与 v-for 同元素 -->
  <!-- <ul>
    <li v-for="todo in todos" v-if="!todo.completed" :key="todo.id">
      {{ todo.title }}
    </li>
  </ul> -->
</template>
```

### v-for 必须指定 key

使用 `v-for` 渲染列表时，必须为每个元素提供唯一的 `key` 属性。优先使用数据中的唯一标识字段（如 `id`），避免使用索引作为 key。

```vue
<template>
  <ul>
    <li v-for="item in items" :key="item.id">
      {{ item.name }}
    </li>
  </ul>
</template>
```

### 模板逻辑应保持简洁

模板中应避免复杂的表达式和条件逻辑。条件渲染和派生状态应优先使用计算属性（`computed`）封装，确保模板的可读性和可维护性。

```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: 'loading' | 'success' | 'error' | 'empty'
}>()

/** 根据状态值返回对应的提示文案 */
const statusMessage = computed(() => {
  const map: Record<string, string> = {
    loading: '正在加载...',
    success: '加载成功',
    error: '加载失败，请重试',
    empty: '暂无数据'
  }
  return map[props.status] || '未知状态'
})

/** 是否为加载完成状态 */
const isFinished = computed(() =>
  ['success', 'error', 'empty'].includes(props.status)
)
</script>

<template>
  <div>
    <!-- 使用计算属性替代模板内联表达式 -->
    <p>{{ statusMessage }}</p>
    <button v-if="isFinished" @click="onRetry">重新加载</button>
  </div>
</template>
```

### 组件 JSDoc 注释

每个组件应在 `<script setup>` 顶部或模板注释块中添加 JSDoc 注释，说明组件的用途、使用场景以及注意事项。

```vue
<script setup lang="ts">
/**
 * 文件上传组件
 *
 * 支持单文件和多文件上传，自动校验文件类型和大小。
 * 上传进度通过 onProgress 回调暴露给父组件。
 * 文件类型白名单通过 accept 属性配置。
 *
 * @usage
 * ```vue
 * <file-upload
 *   :accept="['.pdf', '.docx']"
 *   :max-size="10 * 1024 * 1024"
 *   @upload-complete="handleUploadComplete"
 * />
 * ```
 */
// ...
</script>
```

## Composable 设计规范

Composable（组合式函数）是 Vue 3 中用于封装和复用有状态逻辑的核心模式。遵循以下规范可以确保 composable 的可维护性、可测试性和可组合性。

### 单一职责原则

一个 composable 应仅封装一个领域概念。如果某个 composable 同时管理任务生命周期、数据查询和 UI 提示，则应将不同职责拆分到独立的 composable 中。

### 拆分时机

当 composable 内部出现多个不直接相关的关注点时，应提取独立职责。例如从 `useIngest` 中拆分出 `useIngestTask`（任务生命周期）和 `useAvailableSources`（数据源查询），各自只做一件事。

```typescript
// 错误做法：一个 composable 承载多个领域概念
// composables/useIngest.ts
export function useIngest() {
  const sources = ref<Source[]>([])
  const taskId = ref<string | null>(null)
  const status = ref<'idle' | 'running' | 'done'>('idle')
  const hint = ref('')

  async function fetchSources() { /* ... */ }
  async function startTask(sourceId: string) { /* ... */ }
  function showHint(msg: string) { hint.value = msg; setTimeout(() => hint.value = '', 3000) }

  return { sources, taskId, status, hint, fetchSources, startTask, showHint }
}

// 正确做法：拆分为多个 composable
// composables/useAvailableSources.ts
export function useAvailableSources() {
  const sources = ref<Source[]>([])
  const loading = ref(false)

  async function fetchSources() { /* ... */ }

  return { sources, loading, fetchSources }
}

// composables/useIngestTask.ts
export function useIngestTask() {
  const taskId = ref<string | null>(null)
  const status = ref<'idle' | 'running' | 'done'>('idle')

  async function startTask(sourceId: string) { /* ... */ }

  return { taskId, status, startTask }
}
```

### 避免直接操作全局副作用

不要在 composable 内部直接引用 `sessionStorage`、`localStorage`、`window` 或 toast 单例。应通过参数或适配器注入这些依赖，以便在测试时可以替换为 mock 实现。

```typescript
// 错误做法：直接依赖全局对象
export function useTheme() {
  const theme = ref(localStorage.getItem('theme') || 'light')
  function setTheme(val: string) {
    theme.value = val
    localStorage.setItem('theme', val)
  }
  return { theme, setTheme }
}

// 正确做法：通过参数注入依赖
export function useTheme(storage: Storage = localStorage) {
  const theme = ref(storage.getItem('theme') || 'light')
  function setTheme(val: string) {
    theme.value = val
    storage.setItem('theme', val)
  }
  return { theme, setTheme }
}
```

### 最小化导出接口

只导出调用方确实需要的 ref 和方法。内部使用的轮询定时器、中间处理函数等应保持私有，不暴露到 composable 的返回值中。

```typescript
// 错误做法：暴露内部实现细节
export function usePolling() {
  const timer = ref<number | null>(null)
  const data = ref<Data | null>(null)

  function start() {
    timer.value = window.setInterval(fetch, 1000)
  }
  function stop() {
    if (timer.value !== null) {
      clearInterval(timer.value)
      timer.value = null
    }
  }
  return { timer, data, start, stop }
}

// 正确做法：隐藏内部细节
export function usePolling() {
  const data = ref<Data | null>(null)
  let timer: number | null = null

  function start() {
    timer = window.setInterval(fetch, 1000)
  }
  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  return { data, start, stop }
}
```

### 使用 computed 派生状态

将 `statusText`、`isIndeterminate`、`progressRatio` 等派生状态以 `computed` 属性暴露，而不是让视图层重复实现相同的逻辑判断。

```typescript
export function useIngestTask() {
  const status = ref<'idle' | 'running' | 'done'>('idle')
  const progress = ref(0)

  /** 根据当前状态返回对应的中文提示文案 */
  const statusText = computed(() => {
    const map: Record<string, string> = {
      idle: '待开始',
      running: '正在摄入',
      done: '摄入完成'
    }
    return map[status.value] || '未知状态'
  })

  /** 是否为不确定进度的加载中状态（进度为 0 但仍处于运行中） */
  const isIndeterminate = computed(() =>
    status.value === 'running' && progress.value === 0
  )

  /** 归一化的进度比例（0 ~ 1） */
  const progressRatio = computed(() =>
    Math.min(progress.value / 100, 1)
  )

  return { status, progress, statusText, isIndeterminate, progressRatio }
}
```

### 保持 composable 与框架解耦

业务规则应放在纯工具函数或常量模块中（如 `constants/ingest.js`、`utils/`），composable 只负责编排响应式状态和副作用。这样业务逻辑不依赖 Vue 框架，便于单元测试和复用。

```typescript
// constants/ingest.ts — 纯业务逻辑，不依赖 Vue
export const INGEST_STATUS = {
  IDLE: 'idle',
  RUNNING: 'running',
  DONE: 'done'
} as const

export const STATUS_LABEL: Record<string, string> = {
  [INGEST_STATUS.IDLE]: '待开始',
  [INGEST_STATUS.RUNNING]: '正在摄入',
  [INGEST_STATUS.DONE]: '摄入完成'
}

export function isTerminalStatus(status: string): boolean {
  return status === INGEST_STATUS.DONE
}
```

```typescript
// composables/useIngestTask.ts — 只编排响应式，不包含业务规则
import { INGEST_STATUS, STATUS_LABEL, isTerminalStatus } from '@/constants/ingest'

export function useIngestTask() {
  const status = ref<string>(INGEST_STATUS.IDLE)

  const statusText = computed(() => STATUS_LABEL[status.value] || '未知状态')
  const isFinished = computed(() => isTerminalStatus(status.value))

  return { status, statusText, isFinished }
}
```

### 完整示例对比

以下展示浅层 `useIngest` 与深层分离设计的差异。

**浅层设计 — `useIngest` 承担过多职责：**

```typescript
// composables/useIngest.ts
export function useIngest() {
  const sources = ref<Source[]>([])
  const loading = ref(false)
  const error = ref('')
  const taskId = ref<string | null>(null)
  const taskStatus = ref<'idle' | 'running' | 'done'>('idle')
  const timer = ref<number | null>(null)
  const toast = ref('')

  async function loadSources() {
    loading.value = true
    try {
      sources.value = await api.getSources()
    } catch (e) {
      error.value = '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function startIngest() {
    taskStatus.value = 'running'
    const { id } = await api.startTask(sources.value[0].id)
    taskId.value = id
    timer.value = window.setInterval(pollStatus, 1000)
  }

  async function pollStatus() {
    const result = await api.getTask(taskId.value!)
    taskStatus.value = result.status
    if (result.status === 'done') {
      clearInterval(timer.value!)
      toast.value = '摄入完成'
    }
  }

  return { sources, loading, error, taskStatus, toast, loadSources, startIngest }
}
```

**深层分离设计 — 拆分职责、注入依赖、提取常量：**

```typescript
// constants/ingest.ts
export const POLL_INTERVAL_MS = 1000
export const TASK_STATUS = {
  IDLE: 'idle', RUNNING: 'running', DONE: 'done'
} as const

// composables/useAvailableSources.ts
export function useAvailableSources() {
  const sources = ref<Source[]>([])
  const loading = ref(false)
  const error = ref('')

  async function loadSources() {
    loading.value = true
    try {
      sources.value = await api.getSources()
    } catch {
      error.value = '加载失败'
    } finally {
      loading.value = false
    }
  }

  return { sources, loading, error, loadSources }
}

// composables/useIngestTask.ts
import { POLL_INTERVAL_MS, TASK_STATUS } from '@/constants/ingest'

export function useIngestTask(opts: {
  onToast?: (msg: string) => void
  setInterval?: typeof setInterval
  clearInterval?: typeof clearInterval
} = {}) {
  const { onToast, setInterval = window.setInterval, clearInterval = window.clearInterval } = opts
  const taskId = ref<string | null>(null)
  const status = ref<string>(TASK_STATUS.IDLE)
  let timer: number | null = null

  async function start(sourceId: string) {
    status.value = TASK_STATUS.RUNNING
    const { id } = await api.startTask(sourceId)
    taskId.value = id
    timer = setInterval(pollStatus, POLL_INTERVAL_MS)
  }

  async function pollStatus() {
    const result = await api.getTask(taskId.value!)
    status.value = result.status
    if (result.status === TASK_STATUS.DONE) {
      if (timer !== null) clearInterval(timer)
      onToast?.('摄入完成')
    }
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    status.value = TASK_STATUS.IDLE
  }

  /** 是否处于运行中 */
  const isRunning = computed(() => status.value === TASK_STATUS.RUNNING)
  /** 是否已完成 */
  const isDone = computed(() => status.value === TASK_STATUS.DONE)

  return { taskId, status, isRunning, isDone, start, stop }
}
```

## 前端测试规范

前端项目采用 Vitest + Vue Test Utils 作为测试框架。以下规范覆盖测试文件的组织方式、各类测试的编写要点以及常见注意事项。

### 测试文件存放与命名

测试文件统一存放于 `src/__tests__/` 目录下，目录结构镜像源码结构以便快速定位。也可以选择在源文件旁放置 `__tests__/` 目录进行 co-locate 管理，团队内统一一种方式即可。

测试文件命名采用 `*.test.js` 或 `*.test.ts` 格式，与源文件同名。例如 `utils/format.js` 对应的测试文件为 `__tests__/utils/format.test.js`。

### 纯工具函数测试

对于不依赖 Vue 响应式系统的纯工具函数，应直接导入并调用，使用代表性的输入数据覆盖正常路径、边界值和异常情况。

```typescript
// utils/format.ts
export function formatFileSize(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes';
  const units = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(decimals))} ${units[i]}`;
}
```

```typescript
// __tests__/utils/format.test.ts
import { describe, it, expect } from 'vitest'
import { formatFileSize } from '@/utils/format'

describe('formatFileSize', () => {
  it('should return "0 Bytes" when bytes is 0', () => {
    expect(formatFileSize(0)).toBe('0 Bytes')
  })

  it('should format bytes correctly', () => {
    expect(formatFileSize(1024)).toBe('1.00 KB')
    expect(formatFileSize(1048576)).toBe('1.00 MB')
    expect(formatFileSize(1073741824)).toBe('1.00 GB')
  })

  it('should respect decimal places parameter', () => {
    expect(formatFileSize(1536, 1)).toBe('1.5 KB')
  })
})
```

### Composable 测试

测试 composable 时，应在 `setup()` 内部或在异步测试包装器中实例化 composable，从而获得完整的 Vue 响应式上下文。

对于依赖浏览器全局对象（如 `localStorage`、`setInterval`、`fetch`）或第三方 SDK（如 toast）的 composable，应通过参数注入 mock 适配器，测试时传入替代实现。

```typescript
// composables/useIngestTask.ts
export function useIngestTask(opts: {
  onToast?: (msg: string) => void
  setInterval?: typeof setInterval
  clearInterval?: typeof clearInterval
} = {}) {
  const { onToast, setInterval = globalThis.setInterval, clearInterval = globalThis.clearInterval } = opts
  // ...
}
```

```typescript
// __tests__/composables/useIngestTask.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useIngestTask } from '@/composables/useIngestTask'

describe('useIngestTask', () => {
  let onToast: ReturnType<typeof vi.fn>
  let setInterval: ReturnType<typeof vi.fn>
  let clearInterval: ReturnType<typeof vi.fn>

  beforeEach(() => {
    onToast = vi.fn()
    setInterval = vi.fn(() => 42)
    clearInterval = vi.fn()
  })

  it('should start task and set up polling', async () => {
    const { start, status } = useIngestTask({ onToast, setInterval, clearInterval })
    await start('source-1')
    expect(status.value).toBe('running')
    expect(setInterval).toHaveBeenCalledOnce()
  })
})
```

### API Mock 策略

应优先在 `api/index.js` 的导出层或具体的 endpoint 函数层级进行 mock，而不是 mock `globalThis.fetch`。直接 mock fetch 容易遗漏 `Response.headers.get` 等方法的模拟，导致生产代码在调用 `headers.get` 时抛出 `TypeError`。

```typescript
// api/endpoints.js
import { httpClient } from './http'

export async function getSources() {
  const res = await httpClient.get('/api/sources')
  return res.data
}
```

```typescript
// __tests__/api/endpoints.test.ts
import { describe, it, expect, vi } from 'vitest'

// 在 api/index 层级 mock，而非 mock globalThis.fetch
vi.mock('@/api/endpoints', () => ({
  getSources: vi.fn()
}))

import { getSources } from '@/api/endpoints'

describe('getSources', () => {
  it('should return source list', async () => {
    vi.mocked(getSources).mockResolvedValue([
      { id: '1', name: 'Source A' }
    ])
    const result = await getSources()
    expect(result).toHaveLength(1)
  })
})
```

如果确实需要 mock 底层 HTTP 请求，应确保 mock 的 `Response` 对象包含 `headers.get` 等生产代码可能使用的方法。

```typescript
// 当生产代码需要读取响应头时，必须模拟 headers.get
function createMockResponse(data: unknown, headers: Record<string, string> = {}) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
    headers: {
      get: (key: string) => headers[key] ?? null
    }
  }
}
```

### 组件测试

组件测试应关注用户可见的输出和组件发出的事件，避免测试内部 ref 值或私有方法等实现细节。使用 `@vue/test-utils` 的 `mount` 或 `shallowMount` 渲染组件，通过 `find`、`findComponent`、`text()`、`emitted()` 等 API 验证行为。

```typescript
// __tests__/components/UserCard.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UserCard from '@/components/UserCard.vue'

describe('UserCard', () => {
  it('should display user name', () => {
    const wrapper = mount(UserCard, {
      props: { userName: 'Alice', email: 'alice@example.com' }
    })
    expect(wrapper.text()).toContain('Alice')
  })

  it('should emit card-click when card is clicked', async () => {
    const wrapper = mount(UserCard, {
      props: { userName: 'Alice', userId: 'u-001' }
    })
    await wrapper.find('.card').trigger('click')
    expect(wrapper.emitted('card-click')).toBeTruthy()
    expect(wrapper.emitted('card-click')![0]).toEqual(['u-001'])
  })

  it('should show default avatar when avatarUrl is empty', () => {
    const wrapper = mount(UserCard, {
      props: { userName: 'Bob', avatarUrl: '' }
    })
    const img = wrapper.find('img')
    expect(img.attributes('src')).toBe('/default-avatar.png')
  })
})
```

### 时区感知

涉及时间格式化的测试应固定时区，避免 CI 环境与本地环境的时区差异导致测试失败。可以在测试运行前设置环境变量 `TZ=UTC`，或在测试文件中通过 `vi.setSystemTime` 配合时区信息进行断言。优先选择对本地格式化输出进行断言，而非硬编码 UTC 预期值。

```typescript
// 方式一：在 vitest.config.ts 中全局固定时区
// export default defineConfig({
//   test: {
//     env: { TZ: 'UTC' }
//   }
// })

// 方式二：在测试文件中断言本地格式化输出
describe('时间格式化', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-15T10:30:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should format date in local timezone', () => {
    const result = formatDate(new Date())
    // 断言本地格式化后的字符串，不硬编码 UTC 预期
    expect(result).toBe(
      new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit'
      }).format(new Date('2025-06-15T10:30:00Z'))
    )
  })
})
```

### 浏览器 API Mock

测试使用 `sessionStorage`、`localStorage`、`setInterval` 等浏览器 API 的代码时，应在每个测试之前创建干净的 mock 实现，并在 `beforeEach`/`afterEach` 中重置状态，避免测试间互相影响。

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('useTheme', () => {
  let mockStorage: Record<string, string>

  beforeEach(() => {
    mockStorage = {}
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => mockStorage[key] ?? null,
      setItem: (key: string, value: string) => { mockStorage[key] = value },
      removeItem: (key: string) => { delete mockStorage[key] },
      clear: () => { mockStorage = {} }
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('should return default theme when nothing is stored', () => {
    const { theme } = useTheme()
    expect(theme.value).toBe('light')
  })

  it('should persist theme to storage', () => {
    const { theme, setTheme } = useTheme()
    setTheme('dark')
    expect(theme.value).toBe('dark')
    expect(mockStorage.theme).toBe('dark')
  })
})
```

### 运行测试

使用 `npm test` 或 `npx vitest run` 执行测试。开发阶段可以使用 `npx vitest`（watch 模式）进行迭代。CI 环境中应使用 `npx vitest run --reporter=verbose` 获取详细的测试结果输出。
- **常量名**: 使用 `UPPER_SNAKE_CASE` 或 `camelCase`。当常量值为字符串/数字字面量且全项目通用时，推荐 `UPPER_SNAKE_CASE`。
- **函数名**: 使用 `camelCase`，动词开头（如 `getUser`、`createOrder`、`deleteFile`）。
- **类名与构造函数**: 使用 `PascalCase`。
- **接口名**: 使用 `PascalCase`，推荐以 `I` 开头为可选约定，团队内统一即可。
- **类型别名**: 使用 `PascalCase`。
- **枚举名**: 使用 `PascalCase`，枚举成员使用 `PascalCase` 或 `UPPER_SNAKE_CASE`。
- **文件名**: 使用 `kebab-case`（推荐）或 `camelCase`，团队内统一。
- **目录名**: 使用 `kebab-case`（推荐）。

## TypeScript 特有规范

- **优先使用 interface 而非 type** 来描述对象类型。type 用于联合类型、交叉类型等复杂类型组合。
- **显式标注函数返回值类型**，不依赖 TypeScript 的类型推断。
- **使用 `as const`** 标注不会发生变更的常量对象或数组。
- **避免使用 `any`**，优先使用 `unknown` 并在使用时进行类型收窄。
- **使用 `strictNullChecks`**，确保对 `null` / `undefined` 的处理是显式的。
- **泛型参数** 使用有意义的名称（如 `TData` 而非 `T`），或在简单场景下使用单个大写字母。

## 异步与并发

- **优先使用 `async/await`** 替代裸 `Promise.then().catch()` 链式调用。
- **并发执行多个独立异步任务** 时，使用 `Promise.all()` 或 `Promise.allSettled()`。
  - 当需要所有任务成功完成时使用 `Promise.all()`。
  - 当允许部分任务失败时使用 `Promise.allSettled()`。
- **避免 `async void`**，确保所有异步操作都被 await 或正确处理。
- **控制并发数量**：当需要并发执行大量异步任务时，使用限流机制（如 `p-limit` 库或自定义信号量）。
- **使用 `EventEmitter` 或 `Observable`** 处理流式事件驱动场景。

## 错误处理

- **使用自定义错误类** 继承 `Error`，通过 `name` 属性区分错误类型。
- **不要吞掉异常**：在最外层调用代码中必须有兜底形式的异常捕获。
- **异步错误** 必须被捕获并处理，未捕获的 Promise 拒绝应通过 `process.on('unhandledRejection', ...)` 处理。
- **使用 `try/catch`** 包裹 await 调用，或在顶层统一通过中间件/过滤器处理。
- **错误对象应包含有用信息**：如错误码、上下文数据等。

```typescript
/**
 * 业务异常基类
 *
 * 所有业务异常都应继承该类，通过 code 字段区分具体的错误类型。
 */
class BusinessError extends Error {
  constructor(
    message: string,
    public readonly code: string
  ) {
    super(message);
    this.name = 'BusinessError';
  }
}
```

## 日志记录

- **推荐使用结构化日志**（如 `pino`、`winston`），输出 JSON 格式便于日志收集系统分析。
- **在不同层级按日志级别记录**：`debug`（开发调试）、`info`（正常运行）、`warn`（异常但可恢复）、`error`（需立即关注）。内层模块可使用 `debug` / `warn` 记录操作细节，顶层模块使用 `info` / `error` 记录请求维度信息。
- 日志应包含请求 ID、用户 ID 等上下文信息，以便链路追踪。推荐通过 `AsyncLocalStorage` 实现上下文透传，避免手动透传参数。
- **避免在日志中记录敏感信息**：如密码、Token、身份证号等，必要时进行脱敏处理。
- 推荐使用 `pino` 的子日志（child logger）机制，在执行链路中携带公共上下文，而非手动拼接日志字段。

## 模块导入规范

- **导入顺序** 遵循如下规则，各组之间空一行分隔：
  1. Node.js 内置模块（`fs`、`path` 等）
  2. 第三方依赖（`express`、`lodash` 等）
  3. 项目内部模块（`@/utils`、`@/services` 等）
  4. 相对路径导入（`../`、`./`）
- **避免使用 `* as` 导入**，优先使用具名导入。
- **优先使用 `import type`** 导入仅用于类型的模块，避免运行时引入。
- **路径别名**：如果项目配置了路径别名（如 `@/`），应在导入时统一使用。

## 注释编写技巧

- 注释的内容必须要满足具有**增强可读性和可解释性**的内容特点。
- 要尽可能避免存在无用的注释。
- 注释的语言首选为中文。**但要注意：注释内容中关于代码的部分请使用英文来描述，不需要强制翻译为中文描述。**
- 对于容易被误解读的代码段，务必要加上注释说明。
- 对于接口类型的代码段，请加入注释说明。
- 当一段代码有着过长的内容、或是存在过深的调用逻辑时，请添加注释来说明代码层次。
- **避免注释掉的代码**，如有需要应直接删除，可通过 git 历史找回。

## if/else 的使用

1. 要避免存在过深的 if/else 嵌套结构。这里的过深指的是超过 3 层嵌套关系。
2. 要避免存在过长的 if/else if/else 的结构。这里的过长指的是超过 3 个 else if 的语句使用。
3. 当出现上述 1 与 2 中的情况时，请尝试使用以下方法来重构问题代码：
   - 使用卫语句提前返回
   - 使用 switch 语句或 Map 对象（TypeScript 中可使用 `Record<string, Handler>`）
   - 使用责任链模式
   - 使用策略模式
   - 使用枚举
   - 使用表驱动（配置对象映射）

## 函数设计

- **单一职责原则**：一个函数只做一件事。
- **控制函数长度**：单个函数的行数应控制在 50 行以内（不含注释和空行）。
- **减少参数数量**：当参数超过 3 个时，应使用对象参数（Options Object）模式。
- **默认参数**：使用默认参数值替代运行时的 `||` 或 `??` 判断。
- **纯函数优先**：对于相同的输入总能返回相同输出的函数，优先实现为纯函数。

```typescript
/**
 * 格式化文件大小
 *
 * 将字节数转换为人类可读的文件大小字符串。
 *
 * @param {number} bytes - 文件字节数
 * @param {number} [decimals=2] - 保留的小数位数
 * @returns {string} 格式化后的字符串，如 "1.23 MB"
 */
function formatFileSize(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes';
  const units = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(decimals))} ${units[i]}`;
}
```

## 重试机制实现技巧

- 如果某些功能内需要实现重试机制的相关功能时，可以考虑使用指数退避算法来进行实现。
- 推荐将指数退避算法独立实现为一个通用工具函数。
- 应设置最大重试次数，避免无限重试。
- 建议引入 jitter（随机抖动），避免多个客户端同时重试造成雪崩。

```typescript
/**
 * 指数退避延迟计算
 *
 * @param {number} attempt - 当前重试次数（从 0 开始）
 * @param {number} [baseMs=1000] - 基础延迟毫秒数
 * @param {number} [maxMs=30000] - 最大延迟毫秒数
 * @returns {number} 本次重试应等待的毫秒数
 */
function exponentialBackoff(
  attempt: number,
  baseMs: number = 1000,
  maxMs: number = 30000
): number {
  const delay = Math.min(baseMs * Math.pow(2, attempt), maxMs);
  const jitter = Math.random() * delay * 0.1; // 10% 的随机抖动
  return delay + jitter;
}
```

## 配置管理

- 使用环境变量管理配置，推荐通过 `dotenv` 加载 `.env` 文件。
- 所有配置项应集中管理在一个配置模块中，而非散布在各处直接读取 `process.env`。
- 配置模块应提供类型定义，确保配置项类型安全。
- 敏感信息（密码、Token、密钥等）不得硬编码在代码中，必须通过环境变量或密钥管理服务获取。
- `.env.example` 文件应提交到版本管理，实际 `.env` 文件应通过 `.gitignore` 排除。

## 包管理

- 推荐使用 `pnpm` 作为包管理器（如与 CI/CD 环境协商后也可使用 `npm` 或 `yarn`）。
- `package.json` 中的依赖应明确版本号，避免使用 `^`、`~` 等范围限定符导致不可预期的版本升级。
- 生产依赖（`dependencies`）与开发依赖（`devDependencies`）要严格区分。
- 定期使用 `npm audit` 或 `pnpm audit` 检查依赖安全漏洞。
- 锁定文件（`pnpm-lock.yaml` / `package-lock.json`）应提交到版本管理。

## ESLint 与 Prettier

- 项目应统一配置 ESLint 和 Prettier，并在提交前通过 lint-staged 进行检查。
- ESLint 推荐使用 flat config（`eslint.config.mjs`），配合 `typescript-eslint` 插件进行类型感知的 lint 检查。
- Prettier 的格式化规则应与 ESLint 兼容，避免规则冲突。
- 推荐配置规则：
  - 缩进：2 个空格
  - 引号：单引号
  - 分号：始终使用
  - 尾随逗号：ES5 模式（对象和数组的最后一个元素后加逗号）
  - 行宽：100 字符
