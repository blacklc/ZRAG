<!--
  ChatInput 组件
  对话输入区：自动扩展 textarea、模型选择器、发送按钮、键盘快捷键.
  遵循 Apple 风格设计: 圆角 + focus ring + 暗黑模式自适应.
-->
<template>
  <div
    class="sticky bottom-0 z-10 px-2 sm:px-4 py-2 sm:py-3
           bg-white/80 dark:bg-gray-900/80 backdrop-blur-md
           border-t border-gray-200 dark:border-gray-800"
  >
    <!-- 模型选择器行 -->
    <div class="max-w-3xl mx-auto mb-2 flex items-center justify-between">
      <div class="relative" data-testid="model-selector">
        <button
          type="button"
          class="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md
                 text-gray-600 dark:text-gray-300
                 bg-gray-100 dark:bg-gray-800
                 hover:bg-gray-200 dark:hover:bg-gray-700
                 focus:outline-none focus:ring-2 focus:ring-blue-500
                 transition-colors"
          :aria-label="`当前模型: ${currentModelLabel}`"
          :disabled="disabled"
          @click="toggleModelMenu"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-3.5 w-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
          <span>{{ currentModelLabel }}</span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-3 w-3 transition-transform"
            :class="modelMenuOpen ? 'rotate-180' : ''"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <!-- 下拉菜单 -->
        <ul
          v-if="modelMenuOpen"
          class="absolute bottom-full mb-1 left-0 min-w-[180px]
                 bg-white dark:bg-gray-800
                 border border-gray-200 dark:border-gray-700
                 rounded-md shadow-lg overflow-hidden"
          role="listbox"
        >
          <li
            v-for="opt in modelOptions"
            :key="opt.value"
            role="option"
            :aria-selected="opt.value === model"
            class="px-3 py-1.5 text-sm cursor-pointer
                   hover:bg-gray-100 dark:hover:bg-gray-700
                   transition-colors"
            :class="
              opt.value === model
                ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30'
                : 'text-gray-700 dark:text-gray-300'
            "
            :data-testid="`model-option-${opt.value}`"
            @click="selectModel(opt.value)"
          >
            {{ opt.label }}
          </li>
        </ul>
      </div>

      <div class="text-xs text-gray-400 dark:text-gray-500">
        Enter 发送 · Shift+Enter 换行
      </div>
    </div>

    <!-- 输入区 -->
    <div
      class="max-w-3xl mx-auto flex items-end gap-2
             bg-white dark:bg-gray-800
             border border-gray-300 dark:border-gray-700
             rounded-2xl shadow-sm
             focus-within:ring-2 focus-within:ring-blue-500
             transition-shadow"
    >
      <textarea
        ref="textareaRef"
        :value="modelValue"
        rows="1"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-label="placeholder"
        data-testid="chat-input-textarea"
        class="flex-1 resize-none bg-transparent
               px-4 py-3
               text-sm text-gray-900 dark:text-gray-100
               placeholder-gray-400 dark:placeholder-gray-500
               focus:outline-none
               disabled:opacity-50 disabled:cursor-not-allowed
               overflow-y-auto"
        :style="textareaStyle"
        @input="onInput"
        @keydown="onKeydown"
      />

      <button
        type="button"
        :disabled="!canSend"
        :aria-label="loading ? '正在发送' : '发送消息'"
        data-testid="chat-input-send-btn"
        class="m-2 p-2 rounded-full
               text-white bg-blue-600 hover:bg-blue-700
               disabled:bg-gray-300 dark:disabled:bg-gray-700
               disabled:cursor-not-allowed
               focus:outline-none focus:ring-2 focus:ring-blue-500
               transition-colors"
        @click="onSendClick"
      >
        <!-- 加载状态: 旋转 spinner -->
        <svg
          v-if="loading"
          xmlns="http://www.w3.org/2000/svg"
          class="h-4 w-4 animate-spin"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            class="opacity-25"
            cx="12" cy="12" r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        <!-- 正常状态: 发送图标 -->
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          class="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M5 12h14M12 5l7 7-7 7"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatInput 组件
 *
 * 对话输入区域, 提供以下能力:
 * - 自动扩展 textarea (最大 MAX_ROWS 行, 通过 scrollHeight 调整)
 * - 模型选择器 (下拉菜单, 暂不发送到后端, 仅 emit 事件)
 * - 键盘快捷键: Enter 发送, Shift+Enter 换行
 * - 发送按钮在空文本或 loading 状态时禁用
 * - 加载状态显示旋转 spinner
 * - 暗黑模式自适应
 */
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'

/** 模型选择器根节点的 data-testid, 用于外部点击关闭 */
const MODEL_SELECTOR_TESTID = 'model-selector'
/** textarea 最大行数 (用于自动扩展高度上限) */
const MAX_ROWS = 6
/** 单行高度参考值 (与 rows=1 时的 scrollHeight 对齐) */
const SINGLE_ROW_HEIGHT = 24

const props = defineProps({
  /** 双向绑定的输入文本 (v-model) */
  modelValue: {
    type: String,
    default: '',
  },
  /** 当前选中的模型标识 */
  model: {
    type: String,
    default: 'smart-router',
  },
  /** 是否禁用整个输入区 */
  disabled: {
    type: Boolean,
    default: false,
  },
  /** 是否正在加载 (发送按钮显示 spinner) */
  loading: {
    type: Boolean,
    default: false,
  },
  /** placeholder 文案 */
  placeholder: {
    type: String,
    default: '向你的知识库提问...',
  },
})

const emit = defineEmits([
  'update:modelValue',
  'send',
  'model-change',
])

/** 可选模型列表 - 静态配置, 暂不与后端联动 */
const modelOptions = [
  { value: 'smart-router',     label: 'Smart Router' },
  { value: 'glm-5',            label: 'GLM-5' },
  { value: 'kimi-k2.6',        label: 'Kimi K2.6' },
  { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
  { value: 'minimax-m2.7',      label: 'MiniMax-M2.7' },
  { value: 'deepseek-v4-pro',  label: 'DeepSeek V4 Pro' },
]

/** textarea DOM 引用 */
const textareaRef = ref(null)
/** 模型下拉菜单开关 */
const modelMenuOpen = ref(false)

/** 当前选中模型的展示标签 */
const currentModelLabel = computed(() => {
  const found = modelOptions.find((opt) => opt.value === props.model)
  return found ? found.label : props.model
})

/** 发送按钮是否可用: 非禁用/非加载/非空文本 */
const canSend = computed(() => {
  return !props.disabled && !props.loading && props.modelValue.trim().length > 0
})

/**
 * textarea 高度样式
 * - 通过 scrollHeight 自动扩展
 * - 上限为 MAX_ROWS 行
 */
const textareaStyle = computed(() => {
  const el = textareaRef.value
  if (!el) return { height: `${SINGLE_ROW_HEIGHT}px` }
  const maxHeight = SINGLE_ROW_HEIGHT * MAX_ROWS
  const targetHeight = Math.min(el.scrollHeight, maxHeight)
  const overflow = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  return {
    height: `${targetHeight}px`,
    maxHeight: `${maxHeight}px`,
    overflowY: overflow,
  }
})

/**
 * 监听 modelValue 变化, 重新计算 textarea 高度
 * 父组件可能通过 v-model 异步更新文本 (例如重置输入)
 */
watch(
  () => props.modelValue,
  () => {
    nextTick(adjustHeight)
  }
)

/**
 * 监听 model 变化, 关闭菜单 (防御性)
 */
watch(
  () => props.model,
  () => {
    modelMenuOpen.value = false
  }
)

/**
 * 组件挂载后绑定点击外部关闭菜单的事件,
 * 卸载时解绑避免内存泄漏.
 */
onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

/** 调整 textarea 高度 (触发 computed 重新读取 scrollHeight) */
function adjustHeight() {
  // 通过访问 textareaRef.value 触发 computed 中对 scrollHeight 的读取
  if (textareaRef.value) {
    // 强制触发响应式依赖: 简单做法是先读 scrollHeight
    void textareaRef.value.scrollHeight
  }
}

/**
 * 输入事件处理: 同步 v-model
 *
 * @param {Event} event - input 事件对象
 * @returns {void}
 */
function onInput(event) {
  emit('update:modelValue', event.target.value)
}

/**
 * 键盘事件处理
 * - Enter (无 Shift): 触发 send 事件
 * - Shift+Enter: 保留默认行为 (换行)
 *
 * @param {KeyboardEvent} event - keydown 事件对象
 * @returns {void}
 */
function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    doSend()
  }
  // Shift+Enter 走默认行为, 不处理
}

/** 发送按钮点击处理 */
function onSendClick() {
  doSend()
}

/** 实际执行发送动作: trim 后非空才发出 */
function doSend() {
  if (!canSend.value) return
  const query = props.modelValue.trim()
  if (!query) return
  emit('send', query)
}

/** 切换模型下拉菜单 */
function toggleModelMenu() {
  if (props.disabled) return
  modelMenuOpen.value = !modelMenuOpen.value
}

/**
 * 选择某个模型
 *
 * @param {string} value - 模型标识
 * @returns {void}
 */
function selectModel(value) {
  modelMenuOpen.value = false
  if (value !== props.model) {
    emit('model-change', value)
  }
}

/**
 * 文档级点击事件: 点击菜单外部时关闭菜单
 *
 * @param {MouseEvent} event - 鼠标事件
 * @returns {void}
 */
function onDocumentClick(event) {
  if (!modelMenuOpen.value) return
  const selector = document.querySelector(`[data-testid="${MODEL_SELECTOR_TESTID}"]`)
  if (selector && !selector.contains(event.target)) {
    modelMenuOpen.value = false
  }
}
</script>
