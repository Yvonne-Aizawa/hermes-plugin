import type { AvatarState, AvatarTimelineEvent } from './api'

export type TimelinePlayerHandlers = {
  onSpeech?: (event: AvatarTimelineEvent) => void
  onPause?: (event: AvatarTimelineEvent) => void
  onAnimation?: (event: AvatarTimelineEvent) => void
  onExpression?: (event: AvatarTimelineEvent) => void
  onGaze?: (event: AvatarTimelineEvent) => void
  onState?: (state: Partial<AvatarState>, event: AvatarTimelineEvent) => void
  onEvent?: (event: AvatarTimelineEvent) => void
}

export type TimelinePlayer = {
  enqueue: (events: AvatarTimelineEvent[]) => void
  clear: () => void
  dispose: () => void
}

export function createTimelinePlayer(handlers: TimelinePlayerHandlers): TimelinePlayer {
  const timers = new Set<number>()
  const seen = new Set<string>()

  function schedule(event: AvatarTimelineEvent) {
    if (seen.has(event.id)) return
    seen.add(event.id)
    const delayMs = Math.max(0, Number(event.at_ms) || 0)
    const timer = window.setTimeout(() => {
      timers.delete(timer)
      playEvent(event, handlers)
    }, delayMs)
    timers.add(timer)
  }

  function clear() {
    timers.forEach((timer) => window.clearTimeout(timer))
    timers.clear()
  }

  return {
    enqueue(events: AvatarTimelineEvent[]) {
      if (!Array.isArray(events) || events.length === 0) return
      events
        .slice()
        .sort((left, right) => (Number(left.at_ms) || 0) - (Number(right.at_ms) || 0))
        .forEach(schedule)
    },
    clear,
    dispose() {
      clear()
      seen.clear()
    },
  }
}

function playEvent(event: AvatarTimelineEvent, handlers: TimelinePlayerHandlers) {
  handlers.onEvent?.(event)

  switch (event.type) {
    case 'speech.say':
      handlers.onSpeech?.(event)
      break
    case 'speech.pause':
      handlers.onPause?.(event)
      break
    case 'avatar.animation':
      handlers.onAnimation?.(event)
      break
    case 'avatar.expression':
      handlers.onExpression?.(event)
      break
    case 'avatar.gaze':
      handlers.onGaze?.(event)
      break
    case 'avatar.state':
      if (event.state) handlers.onState?.(event.state, event)
      break
    default:
      console.warn('Lumina timeline ignored unknown event type', event)
  }
}
