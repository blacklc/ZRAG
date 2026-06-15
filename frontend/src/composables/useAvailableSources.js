/**
 * 可用数据源业务逻辑 composable
 *
 * 封装可用数据源列表的查询逻辑，独立于摄入任务生命周期管理。
 * 将本逻辑从 useIngest 中拆分出来，使 composable 职责更单一。
 */
import { ref } from 'vue'
import { getAvailableSources } from '../api/endpoints.js'

/**
 * 可用数据源列表 composable
 *
 * @returns {{
 *   availableSources: import('vue').Ref<string[]>,
 *   loadAvailableSources: () => Promise<void>,
 * }}
 */
export function useAvailableSources() {
  /** 可用数据源列表 */
  const availableSources = ref([])

  /**
   * 加载可用数据源列表
   *
   * 调用后端 getAvailableSources() 接口获取数据源名称数组。
   *
   * @returns {Promise<void>}
   */
  async function loadAvailableSources() {
    try {
      const result = await getAvailableSources()
      availableSources.value = result?.sources || []
    } catch (e) {
      availableSources.value = []
    }
  }

  return {
    availableSources,
    loadAvailableSources,
  }
}
