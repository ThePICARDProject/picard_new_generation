const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '')

function buildApiUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath
}

function extractErrorMessage(payload, fallbackMessage) {
  if (!payload) {
    return fallbackMessage
  }

  if (typeof payload === 'string') {
    const message = payload.trim()

    // Reverse proxies and framework-level failures commonly return an HTML
    // error document. Never render that markup as a user-facing API message.
    return message && !message.startsWith('<') ? message : fallbackMessage
  }

  if (Array.isArray(payload)) {
    return payload.join(', ') || fallbackMessage
  }

  if (payload.error) {
    return payload.error
  }

  if (payload.message) {
    return payload.message
  }

  if (payload.errors && typeof payload.errors === 'object') {
    const joinedErrors = Object.values(payload.errors)
      .flat()
      .filter(Boolean)
      .join(', ')

    if (joinedErrors) {
      return joinedErrors
    }
  }

  return fallbackMessage
}

async function parseResponse(response) {
  if (response.status === 204) {
    return null
  }

  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    return response.json()
  }

  return response.text()
}

async function apiRequest(path, options = {}) {
  const { body, csrfToken, headers, ...rest } = options
  const requestHeaders = new Headers(headers || {})

  if (csrfToken) {
    requestHeaders.set('X-CSRFToken', csrfToken)
  }

  let requestBody = body
  if (body !== undefined && !(body instanceof FormData) && typeof body !== 'string') {
    requestHeaders.set('Content-Type', 'application/json')
    requestBody = JSON.stringify(body)
  }

  const response = await fetch(buildApiUrl(path), {
    credentials: 'include',
    ...rest,
    headers: requestHeaders,
    body: requestBody,
  })

  const payload = await parseResponse(response).catch(() => null)

  if (!response.ok) {
    throw new Error(extractErrorMessage(payload, `Request failed with status ${response.status}.`))
  }

  return payload
}

export { API_BASE_URL, apiRequest, buildApiUrl, extractErrorMessage }
