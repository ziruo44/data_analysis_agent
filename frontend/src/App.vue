<template>
  <div class="bg-orbs" aria-hidden="true">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
    <div class="orb orb-4"></div>
  </div>
  <div class="bg-noise" aria-hidden="true"></div>

  <div class="app-layout">
    <Sidebar
      :sessions="sessions"
      :currentThreadId="currentThreadId"
      @select-session="loadSession"
      @new-chat="startNewChat"
      @delete-session="deleteCurrentSession"
    />

    <main class="main">
      <div class="chat-header">
        <FileSelector
          :files="files"
          :selectedFile="selectedFilePath"
          @select="onFileSelect"
          @upload="onFileUpload"
        />
        <span class="file-name" :title="currentFileDisplay">{{ currentFileDisplay }}</span>
      </div>

      <ChatArea
        :messages="messages"
        :processMessage="processMessage"
        :isRunning="isRunning"
        @send="onSend"
      />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import FileSelector from './components/FileSelector.vue'
import ChatArea from './components/ChatArea.vue'
import * as api from './api/index.js'

// 节点 ID → 中文显示名映射
const NODE_DISPLAY_NAMES = {
  data_clean: '数据清洗',
  code_generator: '代码生成',
  sanity_checker: '安全检查',
  code_executor: '代码执行',
  self_reviewer: '结果审查',
  image_analysis: '图表分析',
  report_output: '报告生成',
}

const files = ref([])
const sessions = ref([])
const currentThreadId = ref(null)
const selectedFilePath = ref('')
const messages = ref([])
const processMessage = ref('')
const isRunning = ref(false)
const pollInterval = ref(null)
const currentFileDisplay = ref('')

const pathBasename = (value = '') => value.split(/[\\/]/).pop() || ''

const escapeHtml = (value = '') =>
  String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const normalizePath = (value = '') => String(value).replace(/\\/g, '/')

const toOutputUrl = (chartPath, outputFolder = '') => {
  const normalizedChartPath = normalizePath(chartPath)
  const outputIndex = normalizedChartPath.indexOf('/output/')
  if (outputIndex >= 0) {
    return normalizedChartPath.slice(outputIndex)
  }

  const folderName = pathBasename(outputFolder)
  const fileName = pathBasename(chartPath)
  if (folderName && fileName) {
    return `/output/${folderName}/${fileName}`
  }
  return fileName ? `/output/${fileName}` : ''
}

const renderCodeBlock = (content, language = 'text') => {
  if (!content) return ''
  return `<pre><code class="language-${language}">${escapeHtml(content)}</code></pre>`
}

const renderReportTurn = (turn) =>
  `<div class="turn-block"><div class="turn-label">第 ${turn.turn_number} 轮</div><div class="report-content">${turn.body_html}</div></div>`

const dedupeHistoryTurns = (chatHistory = []) => {
  const seen = new Set()
  return chatHistory.filter((turn) => {
    const key = `${turn.turn_number || 'na'}::${turn.user_prompt || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

const renderHistoryTurn = (turn, outputFolder = '') => {
  const chartUrls = [...new Set((turn.charts || [])
    .map((chartPath) => toOutputUrl(chartPath, turn.output_folder || outputFolder))
    .filter(Boolean))]

  const insights = (turn.chart_insights || [])
    .filter(Boolean)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join('')

  const sections = []

  if (insights) {
    sections.push(`
      <section class="assistant-section">
        <div class="assistant-section-title">本轮结论</div>
        <ul>${insights}</ul>
      </section>
    `)
  }

  if (chartUrls.length > 0) {
    sections.push(`
      <section class="assistant-section">
        <div class="assistant-section-title">生成图表</div>
        <div class="charts-result">
          ${chartUrls.map((url, index) => `<img src="${url}" alt="chart-${index + 1}">`).join('')}
        </div>
      </section>
    `)
  }

  if (turn.execution_log) {
    sections.push(`
      <details class="assistant-details" open>
        <summary>执行输出</summary>
        ${renderCodeBlock(turn.execution_log, 'text')}
      </details>
    `)
  }

  if (turn.generated_code) {
    sections.push(`
      <details class="assistant-details">
        <summary>生成代码</summary>
        ${renderCodeBlock(turn.generated_code, 'python')}
      </details>
    `)
  }

  if (sections.length === 0) {
    sections.push('<p>本轮分析已完成，但未找到可展示的结构化结果。</p>')
  }

  return `
    <div class="turn-block fallback-turn">
      <div class="turn-label">第 ${turn.turn_number || '-'} 轮</div>
      ${sections.join('')}
    </div>
  `
}

// 主题初始化
const initTheme = () => {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') {
    document.documentElement.setAttribute('data-theme', saved)
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
  }
}

const loadFiles = async () => {
  try {
    files.value = await api.listFiles()
  } catch (e) {
    console.error('Failed to load files:', e)
  }
}

const loadSessions = async () => {
  try {
    sessions.value = await api.listSessions()
  } catch (e) {
    console.error('Failed to load sessions:', e)
  }
}

const onFileSelect = (filePath) => {
  selectedFilePath.value = filePath
  currentFileDisplay.value = pathBasename(filePath)
}

const onFileUpload = async (file) => {
  await api.uploadFile(file)
  await loadFiles()
}

const fetchReportTurns = async (threadId) => {
  try {
    const data = await api.getWorkflowReport(threadId)
    return Array.isArray(data.turns) ? data.turns : []
  } catch (e) {
    console.warn('Failed to fetch workflow report, fallback to chat history:', e)
    return []
  }
}

const renderTurnsFromReport = (turns, skipUserMessages = false) => {
  turns.forEach((turn) => {
    if (turn.user_prompt && !skipUserMessages) addMessage('user', turn.user_prompt)
    if (turn.body_html) addMessage('assistant', renderReportTurn(turn))
  })
}

const renderTurnsFromHistory = (chatHistory, outputFolder = '', skipUserMessages = false) => {
  dedupeHistoryTurns(chatHistory).forEach((turn) => {
    if (turn.user_prompt && !skipUserMessages) addMessage('user', turn.user_prompt)
    addMessage('assistant', renderHistoryTurn(turn, outputFolder))
  })
}

const restoreConversation = async (threadId, chatHistory = [], outputFolder = '', skipUserMessages = false) => {
  const reportTurns = await fetchReportTurns(threadId)
  if (reportTurns.length > 0) {
    renderTurnsFromReport(reportTurns, skipUserMessages)
    return
  }

  if (chatHistory.length > 0) {
    renderTurnsFromHistory(chatHistory, outputFolder, skipUserMessages)
  }
}

const appendLatestAssistantTurn = async (threadId) => {
  const reportTurns = await fetchReportTurns(threadId)
  if (reportTurns.length > 0) {
    const lastTurn = reportTurns[reportTurns.length - 1]
    if (lastTurn?.body_html) {
      addMessage('assistant', renderReportTurn(lastTurn))
      return
    }
  }

  const state = await api.getSessionState(threadId)
  const history = dedupeHistoryTurns(state.chat_history || [])
  const lastTurn = history[history.length - 1]
  if (lastTurn) {
    addMessage('assistant', renderHistoryTurn(lastTurn, state.output_folder || ''))
  }
}

const loadSession = async (threadId) => {
  currentThreadId.value = threadId
  try {
    const data = await api.getSessionState(threadId)
    if (data.file_path) {
      const fileName = pathBasename(data.file_path)
      selectedFilePath.value = `storage/${fileName}`
      currentFileDisplay.value = fileName
    } else if (data.output_folder) {
      currentFileDisplay.value = pathBasename(data.output_folder)
    }

    messages.value = []
    const chatHistory = data.chat_history || []

    await restoreConversation(threadId, chatHistory, data.output_folder || '')

    if (messages.value.length === 0 && data.user_prompt) {
      addMessage('user', data.user_prompt)
    }

    await loadSessions()
  } catch (e) {
    console.error('Failed to load session:', e)
  }
}

const startNewChat = () => {
  currentThreadId.value = null
  selectedFilePath.value = ''
  currentFileDisplay.value = ''
  messages.value = []
  processMessage.value = ''
  isRunning.value = false
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
  }
  loadSessions()
}

const deleteCurrentSession = async () => {
  if (!currentThreadId.value) return
  if (!confirm('确定删除当前会话？')) return
  await api.deleteWorkflow(currentThreadId.value)
  startNewChat()
}

const addMessage = (type, content) => {
  messages.value.push({ type, content })
}

const startPolling = async (threadId) => {
  if (pollInterval.value) clearInterval(pollInterval.value)
  let pollCount = 0
  const MAX_POLLS = 150

  pollInterval.value = setInterval(async () => {
    if (!currentThreadId.value || currentThreadId.value !== threadId) return
    pollCount++
    if (pollCount > MAX_POLLS) {
      clearInterval(pollInterval.value)
      isRunning.value = false
      processMessage.value = ''
      addMessage('assistant', '错误: 任务执行超时，请重试')
      return
    }
    try {
      const data = await api.getWorkflowStatus(threadId)
      if (data.status === 'running') {
        const nodeName = data.current_node || ''
        processMessage.value = NODE_DISPLAY_NAMES[nodeName] || (nodeName ? '任务执行' : '任务执行')
      } else if (data.status === 'completed') {
        clearInterval(pollInterval.value)
        isRunning.value = false
        processMessage.value = ''
        await appendLatestAssistantTurn(threadId)
        await loadSessions()
      } else if (data.status === 'error') {
        clearInterval(pollInterval.value)
        isRunning.value = false
        processMessage.value = ''
        const errMsg = data.result?.error || data.detail || '未知错误'
        addMessage('assistant', '错误: ' + errMsg)
      } else if (data.status === 'not_found') {
        clearInterval(pollInterval.value)
        isRunning.value = false
        processMessage.value = ''
        addMessage('assistant', '错误: 工作流状态丢失，请刷新页面后重试')
      }
    } catch (e) {
      console.error('Polling failed:', e)
    }
  }, 2000)
}

const onSend = async (text) => {
  if (!text.trim()) return
  if (!selectedFilePath.value && !currentThreadId.value) {
    alert('请先选择数据文件')
    return
  }
  addMessage('user', text)
  isRunning.value = true
  processMessage.value = '任务启动'

  try {
    if (!currentThreadId.value) {
      const data = await api.startWorkflow(selectedFilePath.value, text)
      if (!data.thread_id) throw new Error(data.detail || '启动失败')
      currentThreadId.value = data.thread_id
      currentFileDisplay.value = selectedFilePath.value.split('/').pop()
      startPolling(data.thread_id)
    } else {
      await api.continueWorkflow(currentThreadId.value, text)
      startPolling(currentThreadId.value)
    }
  } catch (e) {
    isRunning.value = false
    processMessage.value = ''
    addMessage('assistant', '错误: ' + e.message)
  }
}

onMounted(() => {
  initTheme()
  loadFiles()
  loadSessions()
})
</script>
