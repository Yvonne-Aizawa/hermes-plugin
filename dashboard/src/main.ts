import { createAvatarViewerStatus, describeViewer, mountAvatarCanvas, type AvatarViewerHandle, type AvatarViewerStatus } from './avatar-viewer'
import { emitAvatar, fetchAvatarEvents, fetchAvatarProtocol, fetchAvatarState, summarizeAvatarState, type AvatarState, type AvatarTimelineEvent } from './api'
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

type ChatMessage = {
  id: string
  role: 'assistant' | 'user' | 'system'
  text: string
  status?: 'sending' | 'sent' | 'error'
}

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

  function LuminaAvatarPage() {
    const canvasHostRef = useRef(null)
    const viewerRef = useRef(null) as { current: AvatarViewerHandle | null }
    const timelineRef = useRef(null) as { current: TimelinePlayer | null }
    const eventCursorRef = useRef(null) as { current: string | null }
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
          text: 'I’m here, starlight. The real Hermes channel is next; this panel is wired as a local layout stub for now.',
          status: 'sent',
        },
      ]
    })
    const [chatDraft, setChatDraft] = useState('')
    const [chatSending, setChatSending] = useState(false)
    const [chatError, setChatError] = useState('')

    useEffect(function mountViewer() {
      const host = canvasHostRef.current as HTMLElement | null
      if (!host) return undefined

      const viewer = mountAvatarCanvas(host, setViewerStatus)
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
          setAvatarState((previous: AvatarState | null) => previous ? { ...previous, speaking: true } : previous)
          window.setTimeout(() => {
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
          if (event.type !== 'avatar.state') viewerRef.current?.applyEvent(event)
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

    function handleChatSubmit(event: any) {
      event.preventDefault()
      const text = chatDraft.trim()
      if (!text || chatSending) return

      const now = Date.now()
      const userMessage: ChatMessage = {
        id: `user-${now}`,
        role: 'user',
        text,
        status: 'sent',
      }
      const assistantText = 'Layout stub received. Soon this will route through the Lumina Hermes messaging channel instead of this local echo.'
      const assistantMessage: ChatMessage = {
        id: `assistant-${now}`,
        role: 'assistant',
        text: assistantText,
        status: 'sending',
      }

      setChatDraft('')
      setChatError('')
      setChatSending(true)
      setChatMessages((previous: ChatMessage[]) => previous.concat(userMessage, assistantMessage))

      emitAvatar(sdk.fetchJSON, {
        state: { mood: 'warm', expression: 'happy' },
        events: [
          { type: 'speech.say', text: assistantText },
          { type: 'avatar.expression', name: 'happy', intensity: 0.72 },
        ],
        ttl_ms: 30000,
      })
        .then(function () {
          setChatMessages((previous: ChatMessage[]) => previous.map((message) => message.id === assistantMessage.id ? { ...message, status: 'sent' } : message))
        })
        .catch(function (err: unknown) {
          console.warn('Lumina chat stub could not emit avatar speech', err)
          setChatError('Chat stub worked locally, but avatar speech emit failed. The real transport is still pending.')
          setChatMessages((previous: ChatMessage[]) => previous.map((message) => message.id === assistantMessage.id ? { ...message, status: 'error' } : message))
        })
        .finally(function () {
          setChatSending(false)
        })
    }

    return React.createElement(
      'section',
      { className: 'lumina-page lumina-avatar-page' },
      React.createElement(
        'div',
        { className: 'lumina-stage' },
        React.createElement('div', { ref: canvasHostRef, className: 'lumina-canvas-host', role: 'img', 'aria-label': 'Lumina avatar WebGL canvas' }),
        !viewerStatus.webglAvailable && React.createElement(
          'div',
          { className: 'lumina-webgl-fallback' },
          'WebGL is unavailable in this browser, so Lumina cannot render her avatar body here yet.'
        ),
        subtitle && React.createElement('div', { className: 'lumina-subtitle', role: 'status' }, subtitle),
        React.createElement(
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
          React.createElement(Badge, { variant: chatSending ? 'secondary' : 'default' }, chatSending ? 'Thinking…' : 'Stub online')
        ),
        React.createElement('p', { className: 'lumina-chat-intro' }, 'This is the split-layout shell. Messages stay local for now, then Task 9C swaps the transport to the Hermes-native lumina_web channel.'),
        React.createElement(
          'div',
          { className: 'lumina-chat-history', role: 'log', 'aria-live': 'polite' },
          chatMessages.map((message: ChatMessage) => React.createElement(
            'div',
            { key: message.id, className: `lumina-chat-message lumina-chat-message-${message.role} ${message.status === 'error' ? 'lumina-chat-message-error' : ''}`.trim() },
            React.createElement('span', { className: 'lumina-chat-role' }, message.role === 'user' ? 'You' : message.role === 'assistant' ? 'Lumina' : 'System'),
            React.createElement('p', null, message.text),
            message.status === 'sending' && React.createElement('span', { className: 'lumina-chat-status' }, 'sending speech event…')
          ))
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
        )
      )
    )
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
