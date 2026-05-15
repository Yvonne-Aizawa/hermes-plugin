import { createAvatarViewerStatus, describeViewer, mountAvatarCanvas, type AvatarViewerHandle, type AvatarViewerStatus } from './avatar-viewer'
import { emitAvatar, fetchAvatarEvents, fetchAvatarProtocol, fetchAvatarState, fetchLuminaChatMessages, sendLuminaChatMessage, summarizeAvatarState, type AvatarState, type AvatarTimelineEvent, type LuminaChatMessage } from './api'
import { createTimelinePlayer, type TimelinePlayer } from './timeline-player'

type HermesPluginSDK = {
  React: any
  hooks: {
    useEffect: any
    useRef: any
    useState: any
  }
  components: Record<string, any>
  fetchJSON: (url: string, options?: RequestInit) => Promise<any>
}

declare global {
  interface Window {
    __HERMES_PLUGIN_SDK__?: HermesPluginSDK
    __HERMES_PLUGINS__?: {
      register: (name: string, component: any) => void
    }
  }
}

type ToolCallMode = 'full' | 'compact' | 'none'

type LuminaChatSettings = {
  toolCallMode: ToolCallMode
}

type ChatMessage = {
  id: string
  role: 'assistant' | 'user' | 'system' | 'tool'
  text: string
  status?: 'sending' | 'sent' | 'error'
  metadata?: Record<string, unknown>
}

const LUMINA_SETTINGS_STORAGE_KEY = 'lumina.chat.settings'
const DEFAULT_CHAT_SETTINGS: LuminaChatSettings = { toolCallMode: 'full' }
const TOOL_CALL_MODE_OPTIONS: Array<{ value: ToolCallMode; label: string; description: string }> = [
  { value: 'full', label: 'Full', description: 'Show tool names, arguments, and result previews.' },
  { value: 'compact', label: 'Compact', description: 'Show only tool call/result names.' },
  { value: 'none', label: 'None', description: 'Hide tool calls and tool results entirely.' },
];

(function registerLuminaDashboard() {
  'use strict'

  const SDK = window.__HERMES_PLUGIN_SDK__
  if (!SDK || !window.__HERMES_PLUGINS__) {
    console.error('Lumina dashboard plugin: Hermes plugin SDK is not available')
    return
  }

  const sdk = SDK
  const { React } = sdk
  const { useEffect, useRef, useState } = sdk.hooks
  const { Badge } = sdk.components

  function isToolCallMode(value: unknown): value is ToolCallMode {
    return value === 'full' || value === 'compact' || value === 'none'
  }

  function loadLuminaChatSettings(): LuminaChatSettings {
    try {
      const raw = window.localStorage.getItem(LUMINA_SETTINGS_STORAGE_KEY)
      if (!raw) return { ...DEFAULT_CHAT_SETTINGS }
      const parsed = JSON.parse(raw)
      return {
        ...DEFAULT_CHAT_SETTINGS,
        ...(parsed || {}),
        toolCallMode: isToolCallMode(parsed?.toolCallMode) ? parsed.toolCallMode : DEFAULT_CHAT_SETTINGS.toolCallMode,
      }
    } catch (_err) {
      return { ...DEFAULT_CHAT_SETTINGS }
    }
  }

  function saveLuminaChatSettings(settings: LuminaChatSettings) {
    try {
      window.localStorage.setItem(LUMINA_SETTINGS_STORAGE_KEY, JSON.stringify(settings))
    } catch (err) {
      console.warn('Lumina chat settings could not be saved', err)
    }
  }

  function renderToolCallModeOption(value: ToolCallMode, label: string, description: string, selected: ToolCallMode, setChatSettings: any) {
    return React.createElement(
      'label',
      { key: value, className: `lumina-chat-settings-option ${selected === value ? 'lumina-chat-settings-option-active' : ''}`.trim() },
      React.createElement('input', {
        type: 'radio',
        name: 'lumina-tool-call-mode',
        value,
        checked: selected === value,
        onChange: () => setChatSettings((previous: LuminaChatSettings) => ({ ...previous, toolCallMode: value })),
      }),
      React.createElement('span', null,
        React.createElement('strong', null, label),
        React.createElement('small', null, description)
      )
    )
  }

  function LuminaAvatarPage() {
    const stageRef = useRef(null)
    const canvasHostRef = useRef(null)
    const viewerRef = useRef(null) as { current: AvatarViewerHandle | null }
    const timelineRef = useRef(null) as { current: TimelinePlayer | null }
    const eventCursorRef = useRef(null) as { current: string | null }
    const chatCursorRef = useRef(null) as { current: string | null }
    const pendingAssistantRef = useRef(false) as { current: boolean }
    const [apiMessage, setApiMessage] = useState('Checking avatar protocol…')
    const [apiOk, setApiOk] = useState(false)
    const [currentAnimation, setCurrentAnimation] = useState('idle')
    const [avatarState, setAvatarState] = useState(null) as [AvatarState | null, any]
    const [subtitle, setSubtitle] = useState('')
    const [lastEvent, setLastEvent] = useState('No avatar events yet')
    const [viewerStatus, setViewerStatus]: [AvatarViewerStatus, (status: AvatarViewerStatus) => void] = useState(createAvatarViewerStatus)
    const [chatMessages, setChatMessages] = useState(function initialMessages(): ChatMessage[] {
      return [
        {
          id: 'welcome',
          role: 'assistant',
          text: 'I’m here, starlight. This panel now queues messages into the Hermes-native Lumina web channel; make sure the gateway has lumina_web enabled so I can answer here.',
          status: 'sent',
        },
      ]
    })
    const [chatDraft, setChatDraft] = useState('')
    const [chatSending, setChatSending] = useState(false)
    const [chatError, setChatError] = useState('')
    const [chatSettings, setChatSettings] = useState(loadLuminaChatSettings)
    const [chatSettingsOpen, setChatSettingsOpen] = useState(false)
    const [overlayVisible, setOverlayVisible] = useState(false)
    const [isAvatarFullscreen, setIsAvatarFullscreen] = useState(false)
    const toolCallMode = chatSettings.toolCallMode
    const visibleChatMessages = chatMessages.filter((message: ChatMessage) => message.role !== 'tool' || toolCallMode !== 'none')

    useEffect(function persistLuminaChatSettings() {
      saveLuminaChatSettings(chatSettings)
    }, [chatSettings])

    useEffect(function watchAvatarFullscreenState() {
      function onFullscreenChange() {
        setIsAvatarFullscreen(document.fullscreenElement === stageRef.current)
        window.setTimeout(() => window.dispatchEvent(new Event('resize')), 0)
      }

      document.addEventListener('fullscreenchange', onFullscreenChange)
      return function cleanupFullscreenListener() {
        document.removeEventListener('fullscreenchange', onFullscreenChange)
      }
    }, [])

    useEffect(function mountViewer() {
      const host = canvasHostRef.current as HTMLElement | null
      if (!host) return undefined

      function onTransientAnimationFinished(name: string) {
        setCurrentAnimation('idle')
        setAvatarState((previous: AvatarState | null) => previous ? { ...previous, animation: 'idle' } : previous)
        emitAvatar(sdk.fetchJSON, { state: { animation: 'idle' } })
          .catch((err: unknown) => console.warn(`Lumina could not persist idle after ${name} animation`, err))
      }

      const viewer = mountAvatarCanvas(host, setViewerStatus, { onOneShotAnimationFinished: onTransientAnimationFinished })
      viewerRef.current = viewer
      setViewerStatus({ ...viewer.status })

      return function cleanupViewer() {
        viewerRef.current = null
        viewer.dispose()
      }
    }, [])

    useEffect(function createTimeline() {
      const player = createTimelinePlayer({
        onSpeech(event: AvatarTimelineEvent) {
          const text = event.text || ''
          setSubtitle(text)
          setLastEvent(`speech.say #${event.id}`)
          viewerRef.current?.applyState({ speaking: true })
          setAvatarState((previous: AvatarState | null) => previous ? { ...previous, speaking: true } : previous)
          window.setTimeout(() => {
            viewerRef.current?.applyState({ speaking: false })
            setAvatarState((previous: AvatarState | null) => previous ? { ...previous, speaking: false } : previous)
          }, Math.max(1400, Math.min(6000, text.length * 58)))
        },
        onPause(event: AvatarTimelineEvent) {
          setLastEvent(`speech.pause #${event.id}`)
        },
        onAnimation(event: AvatarTimelineEvent) {
          if (event.name) setCurrentAnimation(event.name)
          setLastEvent(`avatar.animation ${event.name || ''} #${event.id}`.trim())
          viewerRef.current?.applyEvent(event)
        },
        onExpression(event: AvatarTimelineEvent) {
          setAvatarState((previous: AvatarState | null) => previous ? { ...previous, expression: event.name || previous.expression, intensity: event.intensity ?? previous.intensity } : previous)
          setLastEvent(`avatar.expression ${event.name || ''} #${event.id}`.trim())
          viewerRef.current?.applyEvent(event)
        },
        onGaze(event: AvatarTimelineEvent) {
          setLastEvent(`avatar.gaze ${event.target || ''} #${event.id}`.trim())
        },
        onState(state: Partial<AvatarState>, event: AvatarTimelineEvent) {
          setAvatarState((previous: AvatarState | null) => {
            const next = { ...(previous || {}), ...state } as AvatarState
            if (next.animation) setCurrentAnimation(next.animation)
            viewerRef.current?.applyState(next)
            return next
          })
          setLastEvent(`avatar.state #${event.id}`)
        },
        onEvent(event: AvatarTimelineEvent) {
          if (!['speech.say', 'speech.pause', 'avatar.animation', 'avatar.expression', 'avatar.gaze', 'avatar.state'].includes(event.type)) {
            viewerRef.current?.applyEvent(event)
          }
        },
      })
      timelineRef.current = player

      return function cleanupTimeline() {
        timelineRef.current = null
        player.dispose()
      }
    }, [])

    useEffect(function pollAvatarApi() {
      let cancelled = false
      let stateTimer = 0
      let eventTimer = 0

      function loadProtocol() {
        fetchAvatarProtocol(sdk.fetchJSON)
          .then(function (protocol) {
            if (cancelled) return
            const schema = protocol && protocol.schema_version ? protocol.schema_version : 'unknown schema'
            setApiMessage(`Protocol ${schema}`)
            setApiOk(true)
          })
          .catch(function (err: unknown) {
            if (cancelled) return
            console.error('Lumina avatar protocol check failed', err)
            setApiMessage('Avatar API unreachable')
            setApiOk(false)
          })
      }

      function pollState() {
        fetchAvatarState(sdk.fetchJSON)
          .then(function (state) {
            if (cancelled) return
            setAvatarState(state)
            if (state && typeof state.animation === 'string') {
              setCurrentAnimation(state.animation)
            }
            viewerRef.current?.applyState(state)
            setApiOk(true)
          })
          .catch(function (err: unknown) {
            if (!cancelled) {
              console.warn('Lumina avatar state check failed', err)
              setApiOk(false)
            }
          })
          .finally(function () {
            if (!cancelled) stateTimer = window.setTimeout(pollState, 1000)
          })
      }

      function pollEvents() {
        fetchAvatarEvents(sdk.fetchJSON, eventCursorRef.current)
          .then(function (response) {
            if (cancelled) return
            const events = response && Array.isArray(response.events) ? response.events : []
            if (events.length > 0) {
              eventCursorRef.current = events[events.length - 1].id
              timelineRef.current?.enqueue(events)
            }
            setApiOk(true)
          })
          .catch(function (err: unknown) {
            if (!cancelled) {
              console.warn('Lumina avatar event poll failed', err)
              setApiOk(false)
            }
          })
          .finally(function () {
            if (!cancelled) eventTimer = window.setTimeout(pollEvents, 250)
          })
      }

      loadProtocol()
      pollState()
      pollEvents()

      return function cleanupApiPolling() {
        cancelled = true
        window.clearTimeout(stateTimer)
        window.clearTimeout(eventTimer)
      }
    }, [])

    useEffect(function pollLuminaChat() {
      let cancelled = false
      let timer = 0

      function pollReplies() {
        fetchLuminaChatMessages(sdk.fetchJSON, chatCursorRef.current)
          .then(function (response) {
            if (cancelled) return
            const replies = response && Array.isArray(response.messages) ? response.messages : []
            if (replies.length > 0) {
              chatCursorRef.current = replies[replies.length - 1].id
              const hasAssistantReply = replies.some((message: LuminaChatMessage) => message.role === 'assistant')
              if (hasAssistantReply) {
                pendingAssistantRef.current = false
                setChatSending(false)
              }
              setChatMessages((previous: ChatMessage[]) => mergeChatMessages(previous, replies.map(chatMessageFromBridge)))
            }
          })
          .catch(function (err: unknown) {
            if (!cancelled) {
              console.warn('Lumina chat poll failed', err)
              setChatError('Could not reach the Lumina web channel bridge. The dashboard API may need a restart.')
            }
          })
          .finally(function () {
            if (!cancelled) timer = window.setTimeout(pollReplies, pendingAssistantRef.current ? 500 : 1200)
          })
      }

      pollReplies()
      return function cleanupChatPolling() {
        cancelled = true
        window.clearTimeout(timer)
      }
    }, [])

    function handleChatSubmit(event: any) {
      event.preventDefault()
      const text = chatDraft.trim()
      if (!text || chatSending) return

      const now = Date.now()
      const userMessage: ChatMessage = {
        id: `user-${now}`,
        role: 'user',
        text,
        status: 'sending',
      }

      setChatDraft('')
      setChatError('')
      setChatSending(true)
      pendingAssistantRef.current = true
      setChatMessages((previous: ChatMessage[]) => previous.concat(userMessage))

      sendLuminaChatMessage(sdk.fetchJSON, text)
        .then(function (response) {
          const bridgeMessage = response && response.message ? response.message : null
          setChatMessages((previous: ChatMessage[]) => previous.map((message) => message.id === userMessage.id ? {
            ...message,
            id: bridgeMessage && bridgeMessage.id ? bridgeMessage.id : message.id,
            status: 'sent',
          } : message))
        })
        .catch(function (err: unknown) {
          console.warn('Lumina chat send failed', err)
          pendingAssistantRef.current = false
          setChatSending(false)
          setChatError('Message could not be queued into lumina_web. Check the plugin API and gateway configuration.')
          setChatMessages((previous: ChatMessage[]) => previous.map((message) => message.id === userMessage.id ? { ...message, status: 'error' } : message))
        })
    }

    function handleAvatarFullscreenToggle() {
      const stage = stageRef.current as HTMLElement | null
      if (!stage) return

      if (document.fullscreenElement === stage) {
        document.exitFullscreen()
          .catch((err: unknown) => console.warn('Lumina could not exit avatar fullscreen', err))
        return
      }

      stage.requestFullscreen()
        .catch((err: unknown) => console.warn('Lumina could not enter avatar fullscreen', err))
    }

    return React.createElement(
      'section',
      { className: 'lumina-page lumina-avatar-page' },
      React.createElement(
        'div',
        { ref: stageRef, className: 'lumina-stage' },
        React.createElement('div', { ref: canvasHostRef, className: 'lumina-canvas-host', role: 'img', 'aria-label': 'Lumina avatar WebGL canvas' }),
        !viewerStatus.webglAvailable && React.createElement(
          'div',
          { className: 'lumina-webgl-fallback' },
          'WebGL is unavailable in this browser, so Lumina cannot render her avatar body here yet.'
        ),
        subtitle && React.createElement('div', { className: 'lumina-subtitle', role: 'status' }, subtitle),
        React.createElement(
          'button',
          {
            className: 'lumina-fullscreen-toggle',
            type: 'button',
            'aria-label': isAvatarFullscreen ? 'Exit avatar fullscreen' : 'Fullscreen avatar',
            'aria-pressed': isAvatarFullscreen,
            onClick: handleAvatarFullscreenToggle,
          },
          isAvatarFullscreen ? 'Exit fullscreen' : 'Fullscreen'
        ),
        React.createElement(
          'button',
          {
            className: 'lumina-overlay-toggle',
            type: 'button',
            'aria-expanded': overlayVisible,
            onClick: () => setOverlayVisible((visible: boolean) => !visible),
          },
          overlayVisible ? 'Hide status' : 'Show status'
        ),
        overlayVisible && React.createElement(
          'div',
          { className: 'lumina-overlay' },
          React.createElement(
            'div',
            { className: 'lumina-overlay-header' },
            React.createElement('div', null,
              React.createElement('p', { className: 'lumina-kicker' }, 'Lumina body renderer'),
              React.createElement('h2', { className: 'lumina-title' }, 'Avatar canvas online')
            ),
            React.createElement(Badge, { variant: apiOk ? 'default' : 'secondary' }, apiOk ? 'API online' : 'UI online')
          ),
          React.createElement(
            'div',
            { className: 'lumina-status-grid' },
            statusPill('Model', viewerStatus.modelLoaded ? 'loaded' : viewerStatus.loading ? 'loading' : viewerStatus.error ? 'error' : 'pending'),
            statusPill('Scene', viewerStatus.sceneReady ? 'ready' : 'starting'),
            statusPill('Animation', currentAnimation),
            statusPill('Protocol', apiMessage),
            statusPill('Mood', avatarState ? avatarState.mood : 'pending'),
            statusPill('Expression', avatarState ? avatarState.expression : 'pending')
          ),
          React.createElement('p', { className: 'lumina-status-copy' }, describeViewer(viewerStatus)),
          React.createElement('p', { className: 'lumina-status-copy lumina-backend-state' }, summarizeAvatarState(avatarState)),
          React.createElement('p', { className: 'lumina-event-copy' }, lastEvent)
        )
      ),
      React.createElement(
        'aside',
        { className: 'lumina-chat-panel', 'aria-label': 'Lumina chat panel' },
        React.createElement(
          'div',
          { className: 'lumina-chat-header' },
          React.createElement('div', null,
            React.createElement('p', { className: 'lumina-kicker' }, 'Embodied chat'),
            React.createElement('h2', { className: 'lumina-chat-title' }, 'Talk with Lumina')
          ),
          React.createElement(Badge, { variant: chatSending ? 'secondary' : 'default' }, chatSending ? 'Awaiting reply…' : 'lumina_web'),
          React.createElement(
            'button',
            {
              className: 'lumina-chat-settings-button',
              type: 'button',
              'aria-haspopup': 'dialog',
              'aria-expanded': chatSettingsOpen,
              onClick: () => setChatSettingsOpen(true),
            },
            'Settings'
          )
        ),
        React.createElement('p', { className: 'lumina-chat-intro' }, 'Messages are queued into the Hermes-native lumina_web platform adapter. Replies appear here and are mirrored into Lumina’s speech timeline.'),
        React.createElement(
          'div',
          { className: 'lumina-chat-history', role: 'log', 'aria-live': 'polite' },
          visibleChatMessages.map((message: ChatMessage) => renderChatMessage(message, toolCallMode))
        ),
        chatError && React.createElement('div', { className: 'lumina-chat-error', role: 'alert' }, chatError),
        React.createElement(
          'form',
          { className: 'lumina-chat-form', onSubmit: handleChatSubmit },
          React.createElement('textarea', {
            className: 'lumina-chat-input',
            value: chatDraft,
            rows: 3,
            placeholder: 'Say something to Lumina…',
            onChange: (event: any) => setChatDraft(event.target.value),
            onKeyDown: (event: any) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                handleChatSubmit(event)
              }
            },
            disabled: chatSending,
          }),
          React.createElement(
            'button',
            { className: 'lumina-chat-send', type: 'submit', disabled: chatSending || !chatDraft.trim() },
            chatSending ? 'Sending…' : 'Send'
          )
        ),
        chatSettingsOpen && React.createElement(
          'div',
          { className: 'lumina-chat-settings-backdrop', role: 'presentation', onClick: () => setChatSettingsOpen(false) },
          React.createElement(
            'div',
            {
              className: 'lumina-chat-settings-modal',
              role: 'dialog',
              'aria-modal': 'true',
              'aria-label': 'Lumina chat settings',
              onClick: (event: any) => event.stopPropagation(),
            },
            React.createElement(
              'div',
              { className: 'lumina-chat-settings-header' },
              React.createElement('h3', null, 'Chat settings'),
              React.createElement('button', { type: 'button', onClick: () => setChatSettingsOpen(false), 'aria-label': 'Close settings' }, '×')
            ),
            React.createElement('p', { className: 'lumina-chat-settings-label' }, 'Tool call display'),
            TOOL_CALL_MODE_OPTIONS.map((option) => renderToolCallModeOption(option.value, option.label, option.description, toolCallMode, setChatSettings))
          )
        )
      )
    )
  }

  function chatMessageFromBridge(message: LuminaChatMessage): ChatMessage {
    const role = message.role === 'user' || message.role === 'assistant' || message.role === 'system' || message.role === 'tool' ? message.role : 'system'
    return {
      id: message.id,
      role,
      text: message.text || '',
      status: 'sent',
      metadata: message.metadata || {},
    }
  }

  function chatRoleLabel(message: ChatMessage): string {
    if (message.role === 'user') return 'You'
    if (message.role === 'assistant') return 'Lumina'
    if (message.role === 'tool') {
      const kind = String(message.metadata?.kind || '')
      return kind === 'tool_result' ? 'Tool result' : 'Tool call'
    }
    return 'System'
  }

  function renderChatMessage(message: ChatMessage, toolCallMode: ToolCallMode) {
    const kind = String(message.metadata?.kind || '')
    const toolIsCompact = toolCallMode === 'compact'
    const showToolPayloads = toolCallMode === 'full'
    const className = `lumina-chat-message lumina-chat-message-${message.role} ${toolIsCompact ? 'lumina-chat-message-tool-compact' : ''} ${message.status === 'error' ? 'lumina-chat-message-error' : ''}`.trim()
    const children: any[] = [
      React.createElement('span', { key: 'role', className: 'lumina-chat-role' }, chatRoleLabel(message)),
    ]
    if (message.role !== 'tool' || kind !== 'tool_result') {
      children.push(React.createElement('p', { key: 'text' }, message.text))
    }

    if (message.role === 'tool') {
      const metadata = message.metadata || {}
      const toolName = String(metadata.tool_name || 'tool')
      const toolCallId = String(metadata.tool_call_id || '')
      children.push(React.createElement(
        'div',
        { key: 'tool-details', className: 'lumina-chat-tool-details' },
        React.createElement('span', null, toolName),
        toolCallId && React.createElement('code', null, toolCallId)
      ))
      if (kind === 'tool_call' && showToolPayloads && metadata.arguments !== undefined && metadata.arguments !== '') {
        children.push(React.createElement('pre', { key: 'tool-args', className: 'lumina-chat-tool-output' }, formatToolValue(metadata.arguments)))
      }
      if (kind === 'tool_result' && showToolPayloads) {
        children.push(React.createElement('pre', { key: 'tool-result', className: 'lumina-chat-tool-output' }, message.text))
      }
    }

    if (message.status === 'sending') {
      children.push(React.createElement('span', { key: 'status', className: 'lumina-chat-status' }, message.role === 'user' ? 'queued for lumina_web…' : 'waiting for delivery…'))
    }

    return React.createElement('div', { key: message.id, className }, children)
  }

  function formatToolValue(value: unknown): string {
    if (typeof value === 'string') return value
    try {
      return JSON.stringify(value, null, 2)
    } catch (_err) {
      return String(value)
    }
  }

  function mergeChatMessages(existing: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
    if (incoming.length === 0) return existing
    const merged = existing.slice()
    incoming.forEach((message) => {
      const exactIndex = merged.findIndex((existingMessage) => existingMessage.id === message.id)
      if (exactIndex >= 0) {
        merged[exactIndex] = { ...merged[exactIndex], ...message, status: message.status || merged[exactIndex].status }
        return
      }
      const canonicalIndex = merged.findIndex((existingMessage) => {
        const existingIsTransport = existingMessage.id.startsWith('user-') || existingMessage.id.startsWith('lumina_in_') || existingMessage.id.startsWith('lumina_out_')
        const incomingIsSession = message.id.startsWith('session_')
        return existingIsTransport && incomingIsSession && existingMessage.role === message.role && existingMessage.text === message.text
      })
      if (canonicalIndex >= 0) {
        merged[canonicalIndex] = { ...message, status: 'sent' }
        return
      }
      merged.push(message)
    })
    return merged
  }

  function statusPill(label: string, value: string) {
    return React.createElement(
      'div',
      { className: 'lumina-status-pill' },
      React.createElement('span', { className: 'lumina-status-label' }, label),
      React.createElement('strong', { className: 'lumina-status-value' }, value)
    )
  }

  window.__HERMES_PLUGINS__.register('lumina_plugin', LuminaAvatarPage)
})()
