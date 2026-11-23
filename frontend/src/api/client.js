// 文件基本信息：frontend/src/api/client.js
// 目的：统一访问 /api/v1，转换 ErrorResponse，并提供 ZIP 下载。
// 输入：请求路径、方法、JSON body 和任务 ID。
// 输出：JSON 数据或 Blob；错误抛出带 code/status/details 的 Error。
// 维护：接口变化必须同步 api.md、openapi.yaml、前端目录索引和契约测试。

const jsonHeaders = { 'Content-Type': 'application/json' }

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...jsonHeaders, ...(options.headers || {}) } })
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.blob()
  if (!response.ok) {
    const error = body?.error || { code: 'INTERNAL_ERROR', message: `HTTP ${response.status}` }
    const failure = new Error(error.message || '请求失败')
    Object.assign(failure, { status: response.status, code: error.code, details: error.details || [] })
    throw failure
  }
  return body
}

export const api = {
  listProjects: () => request('/api/v1/projects'),
  getProject: (projectId) => request(`/api/v1/projects/${encodeURIComponent(projectId)}`),
  createProject: (hfssProjectPath) => request('/api/v1/projects', { method: 'POST', body: JSON.stringify({ hfss_project_path: hfssProjectPath }) }),
  startTraining: (projectId) => request(`/api/v1/projects/${encodeURIComponent(projectId)}/training-tasks`, { method: 'POST', body: '{}' }),
  createEvaluation: (projectId, input, modes) => request(`/api/v1/projects/${encodeURIComponent(projectId)}/evaluation-tasks`, { method: 'POST', body: JSON.stringify({ input, modes }) }),
  getTask: (taskId) => request(`/api/v1/tasks/${encodeURIComponent(taskId)}`),
  getResults: (taskId) => request(`/api/v1/tasks/${encodeURIComponent(taskId)}/results`),
  downloadResults: (taskId) => request(`/api/v1/tasks/${encodeURIComponent(taskId)}/download`, { headers: {} })
}

export async function saveTaskDownload(taskId) {
  const blob = await api.downloadResults(taskId)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${taskId}_result.zip`
  anchor.click()
  URL.revokeObjectURL(url)
}
