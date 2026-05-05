/**
 * chat.js — 数据分析智能体前端交互逻辑
 *
 * 架构说明：
 *   后端是一个多节点 LangGraph 工作流。当前通过轮询 /api/workflow/{id}/status
 *   获取状态与 current_node，根据 current_node 动态更新状态条文案。
 *
 *   如需替换为真正的流式推送（SSE / WebSocket），只需修改 startPolling() 区域，
 *   其他函数（showNodeProgress、lockUI 等）无需变动。
 */

const API_BASE = '';

// =========================================================================
//  开发模式开关：设为 true 时用 setTimeout 模拟多节点流式推进（无需后端）
//  接入真实 API 后改为 false 即可
// =========================================================================
const USE_SIMULATION = false;

let currentThreadId = null;
let selectedFilePath = '';
let pollInterval = null;
let simulationTimer = null;

// =========================================================================
//  节点 ID → 中文显示名映射（与后端 graph.py 中的节点名一一对应）
// =========================================================================
const NODE_DISPLAY_NAMES = {
    'data_clean':      '数据清洗',
    'code_generator':  '代码生成',
    'sanity_checker':  '安全检查',
    'code_executor':   '代码执行',
    'self_reviewer':   '结果审查',
    'image_analysis':  '图表分析',
    'report_output':   '报告生成'
};

// =========================================================================
//  0. 主题切换
// =========================================================================

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    setTheme(current === 'dark' ? 'light' : 'dark');
}

// 初始化主题：localStorage > 系统偏好 > 浅色
(function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') {
        document.documentElement.setAttribute('data-theme', saved);
    } else {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    }
})();

// =========================================================================
//  1. 状态条控制（输入框正上方的玻璃风格进度条）
// =========================================================================

function showNodeProgress(nodeName) {
    const bar = document.getElementById('progressBar');
    const text = document.getElementById('progressText');
    if (!bar || !text) return;
    text.textContent = `工作流：[${nodeName}] 运行中...`;
    bar.style.display = 'flex';
}

function hideNodeProgress() {
    const bar = document.getElementById('progressBar');
    if (bar) bar.style.display = 'none';
}

// =========================================================================
//  1b. 动态过程消息（聊天区域中随节点变化的单条消息）
// =========================================================================

function addOrUpdateProcessMessage(text) {
    removeEmptyState();
    const messagesArea = document.getElementById('messagesArea');
    let existing = document.querySelector('.message.process-message');
    if (existing) {
        existing.querySelector('.message-content').textContent = '处理中：' + text;
        messagesArea.scrollTop = messagesArea.scrollHeight;
    } else {
        const msg = document.createElement('div');
        msg.className = 'message assistant process-message';
        msg.innerHTML = `
            <div class="message-avatar">AI</div>
            <div class="message-content">处理中：${escapeHtml(text)}</div>
        `;
        messagesArea.appendChild(msg);
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }
}

function removeProcessMessage() {
    const existing = document.querySelector('.message.process-message');
    if (existing) existing.remove();
}

// =========================================================================
//  2. UI 锁定控制
// =========================================================================

function lockUI() {
    const sendBtn = document.getElementById('sendBtn');
    const input = document.getElementById('messageInput');
    if (sendBtn) sendBtn.disabled = true;
    if (input) input.disabled = true;
}

function unlockUI() {
    const sendBtn = document.getElementById('sendBtn');
    const input = document.getElementById('messageInput');
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.disabled = false;
    if (input) input.focus();
}

// =========================================================================
//  3. 文件列表与会话管理
// =========================================================================

async function loadFiles() {
    try {
        const res = await fetch(`${API_BASE}/api/files`);
        const files = await res.json();
        const select = document.getElementById('fileSelect');
        select.innerHTML = '<option value="">选择数据文件</option>';
        files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = `storage/${f}`;
            opt.textContent = f;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error('Failed to load files:', e);
    }
}

async function loadSessions() {
    try {
        const list = document.getElementById('sessionsList');
        list.innerHTML = '<div style="padding:15px;color:#999;font-size:12px;">加载中...</div>';

        const res = await fetch(`${API_BASE}/api/threads`);
        const threads = await res.json();

        if (threads.length === 0) {
            list.innerHTML = '<div style="padding:15px;color:#999;font-size:12px;">暂无会话记录</div>';
            return;
        }

        list.innerHTML = threads.map(t => {
            const title = t.session_name || t.thread_id.substring(0, 16) + '...';
            return `
            <div class="session-item ${t.thread_id === currentThreadId ? 'active' : ''}" onclick="loadSession('${t.thread_id}')">
                <div class="session-title" title="${escapeHtml(t.thread_id)}">${escapeHtml(title)}</div>
                <div class="session-meta">${t.checkpoint_count} 步</div>
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load sessions:', e);
        document.getElementById('sessionsList').innerHTML =
            '<div style="padding:15px;color:#999;font-size:12px;">加载失败</div>';
    }
}

async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            await loadFiles();
        }
    } catch (e) {
        console.error('Upload failed:', e);
    }
    input.value = '';
}

function startNewChat() {
    currentThreadId = null;
    if (pollInterval) clearInterval(pollInterval);
    if (simulationTimer) clearTimeout(simulationTimer);
    document.getElementById('messagesArea').innerHTML =
        '<div class="empty-state" id="emptyState"><div class="empty-icon">&#9670;</div><p>选择一个数据文件，输入分析指令开始探索</p></div>';
    document.getElementById('currentFileName').textContent = '';
    loadSessions();
}

async function loadSession(threadId) {
    currentThreadId = threadId;
    loadSessions();

    try {
        const res = await fetch(`${API_BASE}/api/threads/${threadId}/state`);
        if (!res.ok) throw new Error('Failed to load');
        const data = await res.json();

        if (data.file_path) {
            const select = document.getElementById('fileSelect');
            const fileName = data.file_path.split('/').pop();
            for (const opt of select.options) {
                if (opt.value.endsWith('/' + fileName) || opt.text === fileName) {
                    select.value = opt.value;
                    break;
                }
            }
        }

        if (data.output_folder) {
            const folderName = data.output_folder.split('/').pop();
            document.getElementById('currentFileName').textContent = folderName;
        }

        displayMessages(data);
    } catch (e) {
        console.error('Failed to load session:', e);
    }
}

// =========================================================================
//  4. 消息渲染
// =========================================================================

function displayMessages(result) {
    const messagesArea = document.getElementById('messagesArea');
    messagesArea.innerHTML = '';

    const chatHistory = result.chat_history || [];
    const turnCount = chatHistory.length;

    // Show session info card
    messagesArea.innerHTML = `
        <div class="summary-card">
            <div><strong>Thread ID:</strong> ${result.thread_id || currentThreadId}</div>
            <div><strong>数据文件:</strong> ${result.file_path || '无'}</div>
            <div><strong>已清洗:</strong> ${result.cleaned_file_path || '无'}</div>
            <div><strong>数据概况:</strong> ${result.data_profile ? '有' : '无'}</div>
            ${turnCount > 0
                ? `<div><strong>对话轮次:</strong> ${turnCount} 轮</div>`
                : `<div><strong>本轮图表:</strong> ${(result.current_visualization_paths || []).length} 张</div>`}
        </div>
    `;

    if (turnCount > 0) {
        // Load full report with turns
        fetchAndDisplayFullReport(currentThreadId, chatHistory);
    } else {
        // Single turn — no chat_history yet, show user prompt + report
        if (result.user_prompt) {
            addMessage('user', result.user_prompt);
        }
        if (result.output_folder && currentThreadId) {
            fetchAndDisplayReport(currentThreadId);
        }
    }
}

async function fetchAndDisplayFullReport(threadId, chatHistory) {
    try {
        const res = await fetch(`${API_BASE}/api/workflow/${threadId}/report`);
        if (!res.ok) return;
        const data = await res.json();

        const turns = data.turns || [];
        if (turns.length === 0 && chatHistory.length > 0) {
            chatHistory.forEach(function(turn) {
                if (turn.user_prompt) addMessage('user', turn.user_prompt);
            });
            fetchAndDisplayReport(threadId);
            return;
        }

        turns.forEach(function(turn) {
            if (turn.user_prompt) addMessage('user', turn.user_prompt);
            if (turn.body_html) {
                addReportMessage(`<div class="turn-block"><div class="turn-label">第 ${turn.turn_number} 轮</div>${turn.body_html}</div>`);
            }
        });
    } catch (e) {
        console.error('Failed to fetch report:', e);
    }
}

function markdownToHtml(md) {
    // Simple client-side markdown-to-html converter
    if (!md) return '';
    let html = md
        // Code blocks
        .replace(/```python([\s\S]*?)```/g, '<pre><code class="language-python">$1</code></pre>')
        .replace(/```text([\s\S]*?)```/g, '<pre><code class="language-text">$1</code></pre>')
        .replace(/```json([\s\S]*?)```/g, '<pre><code class="language-json">$1</code></pre>')
        // Images
        .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:6px;margin:8px 0;">')
        // Headers
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        // Bold/italic/code
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/_(.+?)_/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Lists
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
        // Paragraphs
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
    // Wrap loose list items
    html = html.replace(/(<li>[\s\S]*?<\/li>)+/g, function(match) {
        return '<ul>' + match + '</ul>';
    });
    return '<p>' + html + '</p>';
}

async function fetchAndDisplayReport(threadId) {
    try {
        const res = await fetch(`${API_BASE}/api/workflow/${threadId}/report`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.exists && data.html) {
            addReportMessage(data.html);
        }
    } catch (e) {
        console.error('Failed to fetch report:', e);
    }
}

function appendWorkflowResult(result) {
    removeProcessMessage();
    addMessage('assistant', '正在生成最终报告...');
    fetchAndDisplayFullReport(currentThreadId, []);
}

function removeEmptyState() {
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.remove();
}

function addMessage(type, content) {
    removeEmptyState();
    const messagesArea = document.getElementById('messagesArea');
    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    msg.innerHTML = `
        <div class="message-avatar">${type === 'user' ? 'U' : 'AI'}</div>
        <div class="message-content">${escapeHtml(content)}</div>
    `;
    messagesArea.appendChild(msg);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addReportMessage(html) {
    removeEmptyState();
    const messagesArea = document.getElementById('messagesArea');
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content report-content" style="max-width:95%;">${html}</div>
    `;
    messagesArea.appendChild(msg);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addCodeMessage(type, code) {
    removeEmptyState();
    const messagesArea = document.getElementById('messagesArea');
    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    msg.innerHTML = `
        <div class="message-avatar">${type === 'user' ? 'U' : 'AI'}</div>
        <div class="message-content"><pre><code>${escapeHtml(code)}</code></pre></div>
    `;
    messagesArea.appendChild(msg);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function addChartsMessage(type, paths) {
    removeEmptyState();
    const messagesArea = document.getElementById('messagesArea');
    const base = '/output/';
    const chartsHtml = paths.map(p => {
        const parts = p.split('/');
        const name = parts.slice(-2).join('/');
        return `<img src="${base}${name}" alt="chart">`;
    }).join('');
    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    msg.innerHTML = `
        <div class="message-avatar">${type === 'user' ? 'U' : 'AI'}</div>
        <div class="message-content"><div class="charts-result">${chartsHtml}</div></div>
    `;
    messagesArea.appendChild(msg);
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =========================================================================
//  5. 键盘事件
// =========================================================================

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// =========================================================================
//  6. 消息发送入口 + 工作流启动/继续
// =========================================================================

function simulateNodeStream() {
    const simulatedNodes = [
        '数据清洗',
        '代码生成',
        '安全检查',
        '代码执行',
        '结果审查',
        '图表分析',
        '报告生成'
    ];

    let step = 0;

    function next() {
        if (step < simulatedNodes.length) {
            showNodeProgress(simulatedNodes[step]);
            step++;
            simulationTimer = setTimeout(next, 1500);
        } else {
            hideNodeProgress();
            unlockUI();
            addMessage('assistant', '（模拟）分析完成！已生成 3 张图表。');
            loadSessions();
        }
    }

    next();
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text) return;

    const filePath = document.getElementById('fileSelect').value;

    if (!USE_SIMULATION && !filePath && !currentThreadId) {
        alert('请先选择数据文件');
        return;
    }

    addMessage('user', text);
    input.value = '';
    input.style.height = 'auto';

    if (USE_SIMULATION) {
        lockUI();
        simulateNodeStream();
        return;
    }

    if (!currentThreadId) {
        startWorkflow(text, filePath);
    } else {
        continueWorkflow(text);
    }
}

async function startWorkflow(userPrompt, filePath) {
    lockUI();
    showNodeProgress('任务启动');

    try {
        const res = await fetch(`${API_BASE}/api/workflow`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath, user_prompt: userPrompt })
        });
        const data = await res.json();
        if (!res.ok) {
            hideNodeProgress();
            unlockUI();
            addMessage('assistant', '错误: 启动任务失败 - ' + (data.detail || '未知错误'));
            return;
        }
        currentThreadId = data.thread_id;
        document.getElementById('currentFileName').textContent = filePath.split('/').pop();
        startPolling();
    } catch (e) {
        console.error('Failed to start workflow:', e);
        hideNodeProgress();
        unlockUI();
        addMessage('assistant', '错误: 启动任务失败 - 网络错误');
    }
}

async function continueWorkflow(userPrompt) {
    lockUI();
    showNodeProgress('任务继续');

    try {
        const res = await fetch(`${API_BASE}/api/workflow/${currentThreadId}/continue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_prompt: userPrompt })
        });
        const data = await res.json();
        if (!res.ok) {
            hideNodeProgress();
            unlockUI();
            addMessage('assistant', '错误: 继续任务失败 - ' + (data.detail || '未知错误'));
            return;
        }
        startPolling();
    } catch (e) {
        console.error('Failed to continue workflow:', e);
        hideNodeProgress();
        unlockUI();
        addMessage('assistant', '错误: 继续任务失败 - 网络错误');
    }
}

// =========================================================================
//  7. 工作流状态监听（轮询；可替换为 SSE / WebSocket）
// =========================================================================

/**
 * 启动轮询监听工作流状态
 *
 * ═══════════════════════════════════════════════════════════════════════
 *  【替换指南】将 setInterval 轮询替换为真正的流式推送时：
 *
 *  方案 A — EventSource (SSE)：
 *    const es = new EventSource(`/api/workflow/${threadId}/stream`);
 *    es.addEventListener('node', (e) => {
 *        const nodeName = JSON.parse(e.data).current_node;
 *        const displayName = NODE_DISPLAY_NAMES[nodeName] || nodeName;
 *        showNodeProgress(displayName);
 *    });
 *    es.addEventListener('done', (e) => { ...  handleCompleted(e) ... });
 *    es.addEventListener('error', (e) => { ...  handleError(e) ... });
 *
 *  方案 B — WebSocket：
 *    const ws = new WebSocket(`ws://localhost:8000/ws/${threadId}`);
 *    ws.onmessage = (e) => {
 *        const payload = JSON.parse(e.data);
 *        if (payload.type === 'node') {
 *            const displayName = NODE_DISPLAY_NAMES[payload.current_node] || payload.current_node;
 *            showNodeProgress(displayName);
 *        } else if (payload.type === 'done') { ... }
 *    };
 * ═══════════════════════════════════════════════════════════════════════
 */
function startPolling() {
    if (pollInterval) clearInterval(pollInterval);

    let pollCount = 0;
    const MAX_POLLS = 150;
    const pollingThreadId = currentThreadId;

    pollInterval = setInterval(async () => {
        if (!currentThreadId || currentThreadId !== pollingThreadId) return;

        pollCount++;
        if (pollCount > MAX_POLLS) {
            clearInterval(pollInterval);
            hideNodeProgress();
            unlockUI();
            addMessage('assistant', '错误: 任务执行超时，请重试');
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/workflow/${currentThreadId}/status`);
            const data = await res.json();

            if (data.status === 'running') {
                const nodeName = data.current_node || '';
                const displayName = NODE_DISPLAY_NAMES[nodeName] || '';
                if (displayName) {
                    showNodeProgress(displayName);
                    addOrUpdateProcessMessage(displayName);
                } else {
                    showNodeProgress('任务执行');
                    addOrUpdateProcessMessage('任务执行');
                }
            } else if (data.status === 'completed') {
                clearInterval(pollInterval);
                hideNodeProgress();
                unlockUI();
                appendWorkflowResult(data.result);
                loadSessions();
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                hideNodeProgress();
                unlockUI();
                const errMsg = data.result?.error || data.detail || '未知错误';
                addMessage('assistant', '错误: ' + errMsg);
            } else if (data.status === 'not_found') {
                clearInterval(pollInterval);
                hideNodeProgress();
                unlockUI();
                addMessage('assistant', '错误: 工作流状态丢失，请刷新页面后重试');
            }
        } catch (e) {
            console.error('Polling failed:', e);
        }
    }, 2000);
}

// =========================================================================
//  8. 会话删除
// =========================================================================

async function deleteCurrentSession() {
    if (!currentThreadId) return;
    if (!confirm('确定删除当前会话？')) return;

    try {
        const res = await fetch(`${API_BASE}/api/workflow/${currentThreadId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            startNewChat();
        }
    } catch (e) {
        console.error('Failed to delete session:', e);
    }
}

// =========================================================================
//  Auto-resize textarea
// =========================================================================
document.addEventListener('DOMContentLoaded', function() {
    const textarea = document.getElementById('messageInput');
    if (textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 150) + 'px';
        });
    }
});

// =========================================================================
//  初始化
// =========================================================================
loadFiles();
loadSessions();
