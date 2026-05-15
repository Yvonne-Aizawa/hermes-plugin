import type { VRM } from '@pixiv/three-vrm'
import type { AvatarState } from './api'

type BoneBaseline = {
  sceneY: number
  headX: number
  headY: number
  headZ: number
}

export type LivelinessController = {
  applyState: (state: Partial<AvatarState>) => void
  noteSpeech: (text?: string) => void
  update: (vrm: VRM | null, elapsed: number, delta: number) => void
}

export function createLivelinessController(): LivelinessController {
  let baseline: BoneBaseline | null = null
  let activeVrm: VRM | null = null
  let speaking = false
  let speakingEnergy = 0
  let nextBlinkAt = 1.4
  let blinkUntil = 0
  let baseExpression = 'neutral'

  function ensureBaseline(vrm: VRM): BoneBaseline {
    if (activeVrm !== vrm) {
      activeVrm = vrm
      const head = getHeadNode(vrm)
      baseline = {
        sceneY: vrm.scene.position.y,
        headX: head?.rotation.x || 0,
        headY: head?.rotation.y || 0,
        headZ: head?.rotation.z || 0,
      }
      nextBlinkAt = 1.4
      blinkUntil = 0
      speakingEnergy = 0
    }
    return baseline as BoneBaseline
  }

  return {
    applyState(state: Partial<AvatarState>) {
      if (typeof state.speaking === 'boolean') {
        speaking = state.speaking
      }
      if (typeof state.expression === 'string') {
        baseExpression = state.expression
      }
    },
    noteSpeech(text?: string) {
      speaking = true
      speakingEnergy = Math.max(speakingEnergy, text && text.length > 0 ? 0.7 : 0.45)
    },
    update(vrm: VRM | null, elapsed: number, delta: number) {
      if (!vrm) return
      const currentBaseline = ensureBaseline(vrm)
      applyBreathing(vrm, currentBaseline, elapsed)
      applySubtleHeadMotion(vrm, currentBaseline, elapsed)
      applyAutomaticBlink(vrm, elapsed, {
        nextBlinkAt,
        blinkUntil,
        scheduleBlink(nextAt: number, until: number) {
          nextBlinkAt = nextAt
          blinkUntil = until
        },
      })
      speakingEnergy = applySpeakingMouthPlaceholder(vrm, elapsed, delta, speaking, speakingEnergy)
      applyIdleExpression(vrm, baseExpression, speaking)
      updateExpressionManager(vrm)
    },
  }
}

export function applyBreathing(vrm: VRM, baseline: BoneBaseline, elapsed: number): void {
  // Tiny whole-body breathing only; do not fight preset VRMA motion.
  vrm.scene.position.y = baseline.sceneY + Math.sin(elapsed * 1.45) * 0.006
}

export function applySubtleHeadMotion(vrm: VRM, baseline: BoneBaseline, elapsed: number): void {
  const head = getHeadNode(vrm)
  if (!head) return
  // Soft camera-facing sway. This avoids IK/face tracking and stays safely procedural.
  head.rotation.x = baseline.headX + Math.sin(elapsed * 0.52) * 0.018
  head.rotation.y = baseline.headY + Math.sin(elapsed * 0.37) * 0.026
  head.rotation.z = baseline.headZ + Math.sin(elapsed * 0.29) * 0.01
}

export function applyAutomaticBlink(
  vrm: VRM,
  elapsed: number,
  blinkState: {
    nextBlinkAt: number
    blinkUntil: number
    scheduleBlink: (nextAt: number, until: number) => void
  }
): void {
  const manager = getExpressionManager(vrm)
  if (!manager) return

  if (elapsed >= blinkState.nextBlinkAt) {
    const blinkLength = 0.12
    const nextDelay = 2.6 + (Math.sin(elapsed * 1.73) + 1) * 1.15
    blinkState.scheduleBlink(elapsed + nextDelay, elapsed + blinkLength)
  }

  const remaining = blinkState.blinkUntil - elapsed
  const blinkAmount = remaining > 0 ? Math.max(0, Math.min(1, remaining / 0.06)) : 0
  setExpressionValue(manager, 'blink', blinkAmount)
}

export function applySpeakingMouthPlaceholder(
  vrm: VRM,
  elapsed: number,
  delta: number,
  speaking: boolean,
  previousEnergy: number
): number {
  const manager = getExpressionManager(vrm)
  if (!manager) return 0

  const target = speaking ? 0.35 + Math.sin(elapsed * 13.0) * 0.18 + Math.sin(elapsed * 7.1) * 0.08 : 0
  const nextEnergy = approach(previousEnergy, Math.max(0, Math.min(0.72, target)), delta * (speaking ? 14 : 10))
  setExpressionValue(manager, 'aa', nextEnergy)
  setExpressionValue(manager, 'oh', speaking ? nextEnergy * 0.26 : 0)
  return nextEnergy
}

function applyIdleExpression(vrm: VRM, baseExpression: string, speaking: boolean): void {
  const manager = getExpressionManager(vrm)
  if (!manager) return
  if (speaking || baseExpression !== 'neutral') return
  // A faint relaxed preset keeps the neutral face from feeling frozen without becoming an emotion system.
  setExpressionValue(manager, 'relaxed', 0.055)
}

function approach(current: number, target: number, amount: number): number {
  const clamped = Math.max(0, Math.min(1, amount))
  return current + (target - current) * clamped
}

function getHeadNode(vrm: VRM): any | null {
  const humanoid: any = (vrm as any).humanoid
  if (!humanoid || typeof humanoid.getNormalizedBoneNode !== 'function') return null
  return humanoid.getNormalizedBoneNode('head')
}

function getExpressionManager(vrm: VRM): any | null {
  const manager: any = (vrm as any).expressionManager
  return manager && typeof manager.setValue === 'function' ? manager : null
}

function setExpressionValue(manager: any, name: string, value: number): void {
  manager.setValue(name, Math.max(0, Math.min(1, value)))
}

function updateExpressionManager(vrm: VRM): void {
  const manager = getExpressionManager(vrm)
  if (manager && typeof manager.update === 'function') {
    manager.update()
  }
}
