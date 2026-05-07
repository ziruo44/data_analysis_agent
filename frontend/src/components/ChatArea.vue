<template>
  <div class="chat-wrapper">
    <div class="messages" ref="messagesAreaRef">
      <div class="messages-inner">
        <div v-if="messages.length === 0 && !processMessage" class="empty-state">
          <div class="empty-icon">&#9670;</div>
          <p>选择一个数据文件，输入分析指令开始探索</p>
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message"
          :class="msg.type === 'user' ? 'user' : 'assistant'"
        >
          <div class="message-avatar">{{ msg.type === 'user' ? 'U' : 'AI' }}</div>
          <div class="message-content" v-html="msg.content"></div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div v-if="processMessage" class="progress-bar">
        <div class="spinner"></div>
        <span>工作流：[{{ processMessage }}] 运行中...</span>
      </div>

      <div class="input-wrapper">
        <textarea
          ref="inputRef"
          v-model="inputText"
          rows="1"
          placeholder="输入分析指令…"
          @keydown="handleKeyDown"
          @input="autoResize"
          :disabled="isRunning"
        ></textarea>
        <button class="send-btn" @click="send" :disabled="isRunning">发送</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  processMessage: { type: String, default: '' },
  isRunning: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])

const inputText = ref('')
const messagesAreaRef = ref(null)
const inputRef = ref(null)

// 新消息到达时自动滚动到底部
watch(() => props.messages.length, () => {
  nextTick(() => {
    if (messagesAreaRef.value) {
      messagesAreaRef.value.scrollTop = messagesAreaRef.value.scrollHeight
    }
  })
})

const send = () => {
  const text = inputText.value.trim()
  if (!text || props.isRunning) return
  emit('send', text)
  inputText.value = ''
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
    }
  })
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

const autoResize = (e) => {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 150) + 'px'
}
</script>
