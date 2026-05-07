const API_BASE = import.meta.env.VITE_API_BASE || ''

export async function listFiles() {
  const res = await fetch(`${API_BASE}/api/files`)
  return res.json()
}

export async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: formData,
  })
  return res.json()
}

export async function listSessions() {
  const res = await fetch(`${API_BASE}/api/threads`)
  return res.json()
}

export async function getSessionState(threadId) {
  const res = await fetch(`${API_BASE}/api/threads/${threadId}/state`)
  return res.json()
}

export async function startWorkflow(filePath, userPrompt) {
  const res = await fetch(`${API_BASE}/api/workflow`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath, user_prompt: userPrompt }),
  })
  return res.json()
}

export async function getWorkflowStatus(threadId) {
  const res = await fetch(`${API_BASE}/api/workflow/${threadId}/status`)
  return res.json()
}

export async function continueWorkflow(threadId, userPrompt) {
  const res = await fetch(`${API_BASE}/api/workflow/${threadId}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_prompt: userPrompt }),
  })
  return res.json()
}

export async function getWorkflowReport(threadId) {
  const res = await fetch(`${API_BASE}/api/workflow/${threadId}/report`)
  return res.json()
}

export async function deleteWorkflow(threadId) {
  const res = await fetch(`${API_BASE}/api/workflow/${threadId}`, {
    method: 'DELETE',
  })
  return res.json()
}
