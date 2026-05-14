export type AvatarState = {
  mood: 'warm' | 'focused' | 'playful' | 'sleepy' | string
  animation: 'idle' | 'wave' | 'walk' | string
  expression: 'neutral' | 'happy' | 'curious' | 'thinking' | string
  speaking: boolean
  gesture: string | null
  intensity: number
  updated_at: string
}

export type AvatarTimelineEvent = {
  id: string
  at_ms: number
  type: 'speech.say' | 'speech.pause' | 'avatar.animation' | 'avatar.expression' | 'avatar.gaze' | 'avatar.state' | string
  turn_id?: string | null
  text?: string
  audio_url?: string | null
  duration_ms?: number
  name?: string
  loop?: boolean
  target?: string
  state?: Partial<AvatarState>
  intensity?: number
  created_at?: string
  ttl_ms?: number
}

export type AvatarEventsResponse = {
  success: boolean
  cursor: string | null
  events: AvatarTimelineEvent[]
  last_event_id: string | null
}

export type AvatarProtocol = {
  schema_version: string
  event_types: string[]
  moods: string[]
  animations: string[]
  expressions: string[]
  gestures: Array<string | null>
  gaze_targets: string[]
  default_ttl_ms: number
  max_events: number
}

export type PluginFetchJSON = (url: string, options?: RequestInit) => Promise<any>

declare global {
  interface Window {
    __HERMES_SESSION_TOKEN__?: string
    __HERMES_BASE_PATH__?: string
  }
}

export function fetchAvatarProtocol(fetchJSON: PluginFetchJSON): Promise<AvatarProtocol> {
  return pluginFetchJSON(fetchJSON, '/api/plugins/lumina_plugin/avatar/protocol')
}

export function fetchAvatarState(fetchJSON: PluginFetchJSON): Promise<AvatarState> {
  return pluginFetchJSON(fetchJSON, '/api/plugins/lumina_plugin/avatar/state')
}

export function fetchAvatarEvents(fetchJSON: PluginFetchJSON, cursor: string | null): Promise<AvatarEventsResponse> {
  const suffix = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return pluginFetchJSON(fetchJSON, `/api/plugins/lumina_plugin/avatar/events${suffix}`)
}

export function summarizeAvatarState(state: AvatarState | null): string {
  if (!state) return 'Awaiting backend avatar state…'
  const parts = [
    `mood ${state.mood}`,
    `expression ${state.expression}`,
    state.speaking ? 'speaking' : 'quiet',
  ]
  if (state.gesture) parts.push(`gesture ${state.gesture}`)
  return parts.join(' · ')
}

async function pluginFetchJSON<T>(fetchJSON: PluginFetchJSON, url: string, options?: RequestInit): Promise<T> {
  // Prefer a direct request when the dashboard-injected token can be recovered.
  // Some dashboard builds remove window.__HERMES_SESSION_TOKEN__ after startup;
  // SDK.fetchJSON then loses auth even though the original inline script is still
  // present in the document.
  if (readDashboardSessionToken()) {
    return fetchJSONWithInjectedToken(url, options) as Promise<T>
  }
  return fetchJSON(url, options)
}

async function fetchJSONWithInjectedToken<T>(url: string, options?: RequestInit): Promise<T> {
  const token = readDashboardSessionToken()
  if (!token) throw new Error('Dashboard session token unavailable for plugin API request')
  const headers = new Headers(options?.headers)
  if (!headers.has('X-Hermes-Session-Token')) {
    headers.set('X-Hermes-Session-Token', token)
  }
  const base = readBasePath()
  const response = await fetch(`${base}${url}`, { ...options, headers })
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`${response.status}: ${text}`)
  }
  return response.json()
}

function readBasePath(): string {
  const raw = window.__HERMES_BASE_PATH__ || readInjectedGlobal('__HERMES_BASE_PATH__') || ''
  if (!raw) return ''
  const withLead = raw.startsWith('/') ? raw : `/${raw}`
  return withLead.replace(/\/+$/, '')
}

function readDashboardSessionToken(): string | null {
  return window.__HERMES_SESSION_TOKEN__ || readInjectedGlobal('__HERMES_SESSION_TOKEN__')
}

function readInjectedGlobal(name: string): string | null {
  const scripts = Array.from(document.scripts)
  const pattern = new RegExp(`window\\.${name}=(["'])(.*?)\\1`)
  for (const script of scripts) {
    const text = script.textContent || ''
    const match = text.match(pattern)
    if (match) return match[2]
  }
  return null
}
