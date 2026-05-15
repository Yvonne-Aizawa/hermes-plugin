import { AnimationClip, AnimationMixer, LoopOnce, LoopRepeat } from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMAnimationLoaderPlugin, createVRMAnimationClip, type VRMAnimation } from '@pixiv/three-vrm-animation'
import type { VRM } from '@pixiv/three-vrm'

const VRMA_BASE_URL = '/dashboard-plugins/lumina_plugin/assets/animations/vrma'

export type LuminaAnimationName =
  | 'idle'
  | 'walk'
  | 'wave'
  | 'greeting'
  | 'peace'
  | 'shoot'
  | 'spin'
  | 'model_pose'
  | 'pose'
  | 'squat'
  | string

export type VrmaPreset = {
  key: string
  label: string
  url: string
  loop: boolean
}

export const VRMA_PRESETS: Record<string, VrmaPreset> = {
  idle: preset('idle', 'Idle loop', 'idle_loop.vrma', true),
  show_full_body: preset('show_full_body', 'Show full body', 'showFullBody.vrma', false),
  greeting: preset('greeting', 'Greeting', 'greeting.vrma', false),
  wave: preset('wave', 'Greeting / wave', 'greeting.vrma', false),
  peace: preset('peace', 'Peace sign', 'peaceSign.vrma', false),
  shoot: preset('shoot', 'Shoot', 'shoot.vrma', false),
  spin: preset('spin', 'Spin', 'spin.vrma', false),
  model_pose: preset('model_pose', 'Model pose', 'modelPose.vrma', false),
  pose: preset('pose', 'Model pose', 'modelPose.vrma', false),
  squat: preset('squat', 'Squat', 'squat.vrma', false),
  dance: preset('dance', 'Dance', 'dance.vrma', false),
}

export type VrmaAnimationController = {
  loadAll: () => Promise<void>
  play: (name: LuminaAnimationName, options?: { loop?: boolean; onFinished?: () => void }) => boolean
  stop: () => void
  update: (delta: number) => void
  dispose: () => void
  loadedNames: () => string[]
}

export function createVrmaAnimationController(vrm: VRM): VrmaAnimationController {
  const mixer = new AnimationMixer(vrm.scene)
  const clips = new Map<string, AnimationClip>()
  const clipsByUrl = new Map<string, AnimationClip>()
  const failed = new Set<string>()
  let activeAction: ReturnType<AnimationMixer['clipAction']> | null = null
  let activeOnFinished: (() => void) | null = null
  let loadPromise: Promise<void> | null = null

  mixer.addEventListener('finished', (event: any) => {
    if (!activeAction || event.action !== activeAction) return
    const onFinished = activeOnFinished
    activeAction = null
    activeOnFinished = null
    onFinished?.()
  })

  async function loadPreset(presetInfo: VrmaPreset): Promise<void> {
    if (clips.has(presetInfo.key) || failed.has(presetInfo.key)) return
    const existingClip = clipsByUrl.get(presetInfo.url)
    if (existingClip) {
      clips.set(presetInfo.key, existingClip)
      return
    }
    try {
      const vrmAnimation = await loadVrma(presetInfo.url)
      const clip = createVRMAnimationClip(vrmAnimation, vrm)
      clip.name = presetInfo.key
      clips.set(presetInfo.key, clip)
      clipsByUrl.set(presetInfo.url, clip)
    } catch (err) {
      failed.add(presetInfo.key)
      console.warn(`Failed to load Lumina VRMA animation ${presetInfo.key}`, err)
    }
  }

  return {
    loadAll() {
      if (!loadPromise) {
        loadPromise = Promise.all(Object.values(VRMA_PRESETS).map(loadPreset)).then(() => undefined)
      }
      return loadPromise
    },
    play(name: LuminaAnimationName, options = {}) {
      const presetInfo = resolvePreset(name)
      if (!presetInfo) return false
      const clip = clips.get(presetInfo.key)
      if (!clip) {
        console.warn(`Lumina VRMA animation not loaded: ${name}`)
        return false
      }

      if (activeAction) {
        activeAction.fadeOut(0.15)
      }
      activeOnFinished = null
      const action = mixer.clipAction(clip)
      action.reset()
      action.clampWhenFinished = true
      const shouldLoop = options.loop ?? presetInfo.loop
      action.setLoop(shouldLoop ? LoopRepeat : LoopOnce, shouldLoop ? Infinity : 1)
      action.fadeIn(0.15)
      action.play()
      activeAction = action
      activeOnFinished = shouldLoop ? null : options.onFinished || null
      return true
    },
    stop() {
      if (activeAction) {
        activeAction.fadeOut(0.15)
        activeAction = null
        activeOnFinished = null
      }
    },
    update(delta: number) {
      mixer.update(delta)
    },
    dispose() {
      mixer.stopAllAction()
      mixer.uncacheRoot(vrm.scene)
      clips.clear()
      clipsByUrl.clear()
      failed.clear()
      activeAction = null
      activeOnFinished = null
    },
    loadedNames() {
      return Array.from(clips.keys()).sort()
    },
  }
}

export function resolvePreset(name: LuminaAnimationName | null | undefined): VrmaPreset | null {
  if (!name || name === 'walk') return null
  return VRMA_PRESETS[name] || null
}

async function loadVrma(url: string): Promise<VRMAnimation> {
  const loader = new GLTFLoader()
  loader.register((parser) => new VRMAnimationLoaderPlugin(parser))
  const gltf = await loader.loadAsync(url)
  const animations = gltf.userData.vrmAnimations as VRMAnimation[] | undefined
  const animation = animations && animations[0]
  if (!animation) {
    throw new Error(`No VRMAnimation found in ${url}`)
  }
  return animation
}

function preset(key: string, label: string, fileName: string, loop: boolean): VrmaPreset {
  return {
    key,
    label,
    url: `${VRMA_BASE_URL}/${fileName}`,
    loop,
  }
}
