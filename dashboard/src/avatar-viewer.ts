import {
  AmbientLight,
  Clock,
  Color,
  DirectionalLight,
  GridHelper,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  REVISION,
  Scene,
  SphereGeometry,
  TorusGeometry,
  WebGLRenderer,
} from 'three'
import { VRMLoaderPlugin, type VRM } from '@pixiv/three-vrm'
import { loadLuminaVrm } from './vrm-loader'
import { createLivelinessController } from './liveliness-controller'
import { createVrmaAnimationController, resolvePreset, type VrmaAnimationController } from './vrma-animation-controller'
import type { AvatarState, AvatarTimelineEvent } from './api'

const LUMINA_VRM_URL = '/dashboard-plugins/lumina_plugin/assets/lumina.vrm'

export type AvatarViewerStatus = {
  webglAvailable: boolean
  threeRevision: string
  vrmRuntime: string
  modelLoaded: boolean
  sceneReady: boolean
  loading: boolean
  modelUrl: string
  error: string | null
}

export type AvatarViewerHandle = {
  status: AvatarViewerStatus
  applyState: (state: Partial<AvatarState>) => void
  applyEvent: (event: AvatarTimelineEvent) => void
  dispose: () => void
}

export function createAvatarViewerStatus(): AvatarViewerStatus {
  return {
    webglAvailable: isWebGLAvailable(),
    threeRevision: REVISION,
    vrmRuntime: typeof VRMLoaderPlugin === 'function' ? 'ready' : 'missing',
    modelLoaded: false,
    sceneReady: false,
    loading: false,
    modelUrl: LUMINA_VRM_URL,
    error: null,
  }
}

export function mountAvatarCanvas(
  container: HTMLElement,
  onStatusChange?: (status: AvatarViewerStatus) => void
): AvatarViewerHandle {
  const status = createAvatarViewerStatus()
  function publish(patch: Partial<AvatarViewerStatus>) {
    Object.assign(status, patch)
    onStatusChange?.({ ...status })
  }

  if (!status.webglAvailable) {
    return {
      status,
      applyState: function applyStateUnavailable() {},
      applyEvent: function applyEventUnavailable() {},
      dispose: function disposeUnavailable() {},
    }
  }

  const scene = new Scene()
  scene.background = new Color(0x070713)

  const camera = new PerspectiveCamera(28, 1, 0.1, 100)
  camera.position.set(0, 1.35, 4.2)
  camera.lookAt(0, 1.25, 0)

  const renderer = new WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0x070713, 0)
  container.appendChild(renderer.domElement)

  const ambient = new AmbientLight(0xaecbff, 1.45)
  scene.add(ambient)

  const key = new DirectionalLight(0xffffff, 2.5)
  key.position.set(2.5, 4, 3)
  scene.add(key)

  const rim = new DirectionalLight(0xb388ff, 1.3)
  rim.position.set(-3, 2, -2)
  scene.add(rim)

  const grid = new GridHelper(4, 24, 0x7048e8, 0x223044)
  grid.position.y = -0.02
  scene.add(grid)

  const placeholder = createLoadingPlaceholder()
  scene.add(placeholder.core, placeholder.halo)

  const clock = new Clock()
  let frameId = 0
  let disposed = false
  let currentVrm: VRM | null = null
  let animationController: VrmaAnimationController | null = null
  let currentExpression = 'neutral'
  let currentAnimation = ''
  const liveliness = createLivelinessController()

  function resize() {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height, false)
  }

  function animate() {
    if (disposed) return
    const delta = clock.getDelta()
    const elapsed = clock.elapsedTime

    if (currentVrm) {
      animationController?.update(delta)
      liveliness.update(currentVrm, elapsed, delta)
      currentVrm.update(delta)
    } else {
      placeholder.core.position.y = 1.25 + Math.sin(elapsed * 1.4) * 0.035
      placeholder.core.rotation.y = elapsed * 0.35
      placeholder.halo.rotation.z = elapsed * 0.42
      placeholder.halo.rotation.y = Math.sin(elapsed * 0.6) * 0.18
    }

    renderer.render(scene, camera)
    frameId = window.requestAnimationFrame(animate)
  }

  async function loadModel() {
    publish({ loading: true, error: null })
    try {
      const vrm = await loadLuminaVrm(LUMINA_VRM_URL)
      if (disposed) return
      currentVrm = vrm
      animationController = createVrmaAnimationController(vrm)
      vrm.scene.position.set(0, 0, 0)
      scene.add(vrm.scene)
      scene.remove(placeholder.core, placeholder.halo)
      disposePlaceholder(placeholder)
      publish({ loading: false, modelLoaded: true, error: null })
      void animationController.loadAll().then(() => {
        if (!disposed) {
          console.debug('Lumina VRMA animations loaded', animationController?.loadedNames())
          if (!currentAnimation && animationController?.play('idle')) {
            currentAnimation = 'idle'
          }
        }
      })
    } catch (err) {
      if (disposed) return
      const message = err instanceof Error ? err.message : String(err)
      console.error('Failed to load Lumina VRM model', err)
      publish({ loading: false, modelLoaded: false, error: message })
    }
  }

  resize()
  window.addEventListener('resize', resize)
  frameId = window.requestAnimationFrame(animate)
  publish({ sceneReady: true })
  void loadModel()

  function playAvatarAnimation(name: string, loop?: boolean, force = false): void {
    const preset = resolvePreset(name)
    if (!preset) return
    if (!force && currentAnimation === name) return
    const started = animationController?.play(name, { loop })
    if (started) {
      currentAnimation = name
    } else {
      void animationController?.loadAll().then(() => {
        if (animationController?.play(name, { loop })) {
          currentAnimation = name
        }
      })
    }
  }

  return {
    status,
    applyState: function applyState(state: Partial<AvatarState>) {
      liveliness.applyState(state)
      if (state.expression) {
        setVrmExpression(currentVrm, state.expression, typeof state.intensity === 'number' ? state.intensity : undefined)
        currentExpression = state.expression
      }
      if (state.animation) {
        playAvatarAnimation(state.animation)
      }
    },
    applyEvent: function applyEvent(event: AvatarTimelineEvent) {
      if (event.type === 'speech.say') {
        liveliness.noteSpeech(event.text)
      }
      if (event.type === 'avatar.expression' && event.name) {
        setVrmExpression(currentVrm, event.name, event.intensity)
        currentExpression = event.name
      }
      if (event.type === 'avatar.state' && event.state) {
        liveliness.applyState(event.state)
        if (event.state.expression && event.state.expression !== currentExpression) {
          setVrmExpression(currentVrm, event.state.expression, event.state.intensity)
          currentExpression = event.state.expression
        }
      }
      if (event.type === 'avatar.animation' && event.name) {
        playAvatarAnimation(event.name, event.loop, true)
      }
    },
    dispose: function disposeViewer() {
      disposed = true
      window.cancelAnimationFrame(frameId)
      window.removeEventListener('resize', resize)
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement)
      }
      disposePlaceholder(placeholder)
      animationController?.dispose()
      disposeVrm(currentVrm)
      renderer.dispose()
    },
  }
}

export function describeViewer(status: AvatarViewerStatus): string {
  if (!status.webglAvailable) {
    return 'WebGL unavailable in this browser.'
  }
  if (status.error) {
    return `VRM load failed: ${status.error}`
  }
  if (status.loading) {
    return 'Loading Lumina’s VRM body…'
  }
  if (!status.sceneReady) {
    return `Three.js r${status.threeRevision} and VRM runtime loaded. Canvas shell is standing by.`
  }
  if (!status.modelLoaded) {
    return `Canvas online with Three.js r${status.threeRevision}. Waiting for ${status.modelUrl}.`
  }
  return `Lumina model loaded with Three.js r${status.threeRevision}.`
}

export function disposeVrm(vrm: VRM | null): void {
  if (!vrm) return
  vrm.scene.traverse((object: any) => {
    if (object.geometry && typeof object.geometry.dispose === 'function') {
      object.geometry.dispose()
    }
    const material = object.material
    if (Array.isArray(material)) {
      material.forEach((item) => item && typeof item.dispose === 'function' && item.dispose())
    } else if (material && typeof material.dispose === 'function') {
      material.dispose()
    }
  })
}

function setVrmExpression(vrm: VRM | null, expression: string, intensity = 1): void {
  if (!vrm || !vrm.expressionManager) return
  const manager: any = vrm.expressionManager
  const amount = Math.max(0, Math.min(1, intensity))
  const knownExpressions = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'aa', 'ih', 'ou', 'ee', 'oh']
  for (const name of knownExpressions) {
    if (typeof manager.setValue === 'function') {
      manager.setValue(name, 0)
    }
  }
  if (expression !== 'neutral' && typeof manager.setValue === 'function') {
    const mapped = expression === 'curious' || expression === 'thinking' ? 'relaxed' : expression
    manager.setValue(mapped, amount)
  }
  if (typeof manager.update === 'function') {
    manager.update()
  }
}

function createLoadingPlaceholder() {
  const core = new Mesh(
    new SphereGeometry(0.38, 48, 32),
    new MeshStandardMaterial({ color: 0xc4b5fd, emissive: 0x7c3aed, emissiveIntensity: 0.45, roughness: 0.32 })
  )
  core.position.set(0, 1.25, 0)

  const halo = new Mesh(
    new TorusGeometry(0.76, 0.018, 12, 96),
    new MeshStandardMaterial({ color: 0x67e8f9, emissive: 0x0891b2, emissiveIntensity: 0.8, roughness: 0.2 })
  )
  halo.position.copy(core.position)
  halo.rotation.x = Math.PI / 2.7

  return { core, halo }
}

function disposePlaceholder(placeholder: ReturnType<typeof createLoadingPlaceholder>): void {
  placeholder.core.geometry.dispose()
  placeholder.halo.geometry.dispose()
  ;(placeholder.core.material as MeshStandardMaterial).dispose()
  ;(placeholder.halo.material as MeshStandardMaterial).dispose()
}

function isWebGLAvailable(): boolean {
  const canvas = document.createElement('canvas')
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
  return Boolean(gl)
}
