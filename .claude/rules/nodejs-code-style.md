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
- 若项目有构建产出物，则这些产出物应存放于 `dist/` 或 `build/` 目录中，并确保通过 `.gitignore` 排除。

## 命名规范

- **变量名**: 使用 `camelCase` 驼峰命名。
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
