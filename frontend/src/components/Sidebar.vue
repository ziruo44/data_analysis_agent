<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo-icon">&#9670;</div>
      <h1>数据分析智能体</h1>
      <button class="theme-toggle" @click="toggleTheme" aria-label="切换主题">
        <svg class="sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
        </svg>
        <svg class="moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
        </svg>
      </button>
    </div>

    <button class="new-chat-btn" @click="$emit('new-chat')">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      新建对话
    </button>

    <div class="sidebar-content">
      <div v-if="sessions.length === 0" class="empty-sessions">暂无会话记录</div>
      <div
        v-for="t in sessions"
        :key="t.thread_id"
        class="session-item"
        :class="{ active: t.thread_id === currentThreadId }"
        @click="$emit('select-session', t.thread_id)"
      >
        <div class="session-title" :title="t.thread_id">{{ t.session_name || t.thread_id.substring(0, 16) + '...' }}</div>
        <div class="session-meta">{{ t.checkpoint_count }} 步</div>
      </div>
    </div>

    <div class="sidebar-footer">
      <button class="delete-btn" @click="$emit('delete-session')">删除当前会话</button>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
  currentThreadId: { type: String, default: null },
})

defineEmits(['select-session', 'new-chat', 'delete-session'])

const toggleTheme = () => {
  const current = document.documentElement.getAttribute('data-theme') || 'light'
  const next = current === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', next)
  localStorage.setItem('theme', next)
}
</script>
