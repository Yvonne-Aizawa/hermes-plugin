import { Object3D } from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRM, VRMUtils } from '@pixiv/three-vrm'

export async function loadLuminaVrm(url: string): Promise<VRM> {
  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))

  const gltf = await loader.loadAsync(url)
  const vrm = gltf.userData.vrm as VRM | undefined
  if (!vrm) {
    throw new Error('Loaded asset did not contain a VRM model')
  }

  prepareVrmScene(vrm.scene)
  VRMUtils.rotateVRM0(vrm)

  return vrm
}

function prepareVrmScene(scene: Object3D): void {
  VRMUtils.removeUnnecessaryVertices(scene)
  VRMUtils.removeUnnecessaryJoints(scene)

  scene.traverse((object) => {
    object.frustumCulled = false
  })
}
