/**
 * Three.js overlay for real lod1.glb poses on the layout board.
 * Camera frustum is synced to the SVG board (ppm/ox/oy) so footprints align.
 * pointer-events: none — drag/select stay on the SVG hit layer.
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

export type GlbPose = {
  key: string;
  url: string;
  x: number;
  y: number;
  yawDeg: number;
  selected?: boolean;
  conflict?: boolean;
  ghost?: boolean;
  tone?: "green" | "yellow" | "red";
};

type Cam = { ppm: number; ox: number; oy: number };

type Props = {
  widthPx: number;
  heightPx: number;
  cam: Cam;
  poses: GlbPose[];
};

const loader = new GLTFLoader();
const templateCache = new Map<string, Promise<THREE.Object3D>>();

function loadTemplate(url: string): Promise<THREE.Object3D> {
  let hit = templateCache.get(url);
  if (!hit) {
    hit = loader.loadAsync(url).then((gltf) => {
      const root = gltf.scene;
      root.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          const mat = mesh.material as THREE.MeshStandardMaterial;
          if (mat && "envMapIntensity" in mat) mat.envMapIntensity = 0.9;
        }
      });
      // P0 lod1 assets are authored length-along-+Z; layout length is local +X.
      root.rotation.y = Math.PI / 2;
      root.updateMatrixWorld(true);
      // Ground the template: minY -> 0, keep XZ center at origin.
      const box = new THREE.Box3().setFromObject(root);
      const center = new THREE.Vector3();
      box.getCenter(center);
      root.position.x -= center.x;
      root.position.z -= center.z;
      root.position.y -= box.min.y;
      root.updateMatrixWorld(true);
      return root;
    });
    templateCache.set(url, hit);
  }
  return hit;
}

const TONE: Record<string, number> = {
  green: 0x2f8f72,
  yellow: 0xc4922e,
  red: 0xce5d50,
  selected: 0x2f6fed,
  conflict: 0xc44b4b,
};

export function GlbBoardLayer({ widthPx, heightPx, cam, poses }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.OrthographicCamera;
    group: THREE.Group;
    rings: THREE.Group;
    pmrem: THREE.PMREMGenerator;
    alive: boolean;
    nodes: Map<string, THREE.Object3D>;
  } | null>(null);

  // Boot / teardown once.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.05, 500);
    // Look straight down: layout (x,y) -> three (x, y=height, z=y), +Z screen-up.
    camera.up.set(0, 0, 1);
    camera.position.set(0, 80, 0);
    camera.lookAt(0, 0, 0);

    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const hemi = new THREE.HemisphereLight(0xfff6e8, 0x6b7a70, 0.9);
    scene.add(hemi);
    const dir = new THREE.DirectionalLight(0xffffff, 1.1);
    dir.position.set(8, 18, 6);
    scene.add(dir);

    const group = new THREE.Group();
    scene.add(group);
    const rings = new THREE.Group();
    scene.add(rings);

    stateRef.current = {
      renderer,
      scene,
      camera,
      group,
      rings,
      pmrem,
      alive: true,
      nodes: new Map(),
    };

    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const st = stateRef.current;
      if (!st) return;
      st.renderer.render(st.scene, st.camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      const st = stateRef.current;
      if (!st) return;
      st.alive = false;
      st.nodes.forEach((node) => {
        st.group.remove(node);
        node.traverse((obj) => {
          const mesh = obj as THREE.Mesh;
          if (mesh.isMesh) {
            mesh.geometry?.dispose?.();
            const mat = mesh.material;
            if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
            else mat?.dispose?.();
          }
        });
      });
      st.nodes.clear();
      st.pmrem.dispose();
      st.renderer.dispose();
      stateRef.current = null;
    };
  }, []);

  // Resize + camera frustum sync to SVG board.
  useEffect(() => {
    const st = stateRef.current;
    if (!st || widthPx <= 0 || heightPx <= 0 || cam.ppm <= 0) return;
    st.renderer.setSize(widthPx, heightPx, false);
    const { camera } = st;
    camera.left = -cam.ox / cam.ppm;
    camera.right = (widthPx - cam.ox) / cam.ppm;
    camera.top = cam.oy / cam.ppm;
    camera.bottom = -(heightPx - cam.oy) / cam.ppm;
    camera.updateProjectionMatrix();
  }, [widthPx, heightPx, cam.ppm, cam.ox, cam.oy]);

  // Sync poses → scene graph.
  useEffect(() => {
    const st = stateRef.current;
    if (!st) return;
    let cancelled = false;
    const wanted = new Set(poses.map((p) => p.key));

    // Remove stale.
    for (const [key, node] of [...st.nodes.entries()]) {
      if (!wanted.has(key)) {
        st.group.remove(node);
        st.nodes.delete(key);
      }
    }

    // Clear rings each sync; rebuild selection/conflict/ghost outlines.
    while (st.rings.children.length) {
      const child = st.rings.children[0];
      st.rings.remove(child);
      const mesh = child as THREE.Mesh;
      mesh.geometry?.dispose?.();
      (mesh.material as THREE.Material)?.dispose?.();
    }

    poses.forEach((pose) => {
      const ringColor =
        pose.conflict ? TONE.conflict : pose.selected ? TONE.selected : pose.tone ? TONE[pose.tone] : null;
      if (ringColor != null) {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.35, 0.55, 32),
          new THREE.MeshBasicMaterial({
            color: ringColor,
            transparent: true,
            opacity: pose.ghost ? 0.55 : 0.85,
            side: THREE.DoubleSide,
            depthTest: false,
          }),
        );
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(pose.x, 0.02, pose.y);
        st.rings.add(ring);
      }

      const existing = st.nodes.get(pose.key);
      if (existing) {
        existing.position.set(pose.x, 0, pose.y);
        existing.rotation.set(0, (-pose.yawDeg * Math.PI) / 180, 0);
        existing.traverse((obj) => {
          const mesh = obj as THREE.Mesh;
          if (mesh.isMesh && mesh.material) {
            const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
            mats.forEach((m) => {
              const std = m as THREE.MeshStandardMaterial;
              if ("opacity" in std) {
                std.transparent = !!pose.ghost;
                std.opacity = pose.ghost ? 0.55 : 1;
              }
            });
          }
        });
        return;
      }

      loadTemplate(pose.url)
        .then((template) => {
          if (cancelled || !stateRef.current?.alive) return;
          if (stateRef.current.nodes.has(pose.key)) return;
          const pivot = new THREE.Group();
          const clone = template.clone(true);
          if (pose.ghost) {
            clone.traverse((obj) => {
              const mesh = obj as THREE.Mesh;
              if (mesh.isMesh && mesh.material) {
                const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
                mats.forEach((m) => {
                  const std = m.clone() as THREE.MeshStandardMaterial;
                  std.transparent = true;
                  std.opacity = 0.55;
                  mesh.material = std;
                });
              }
            });
          }
          pivot.add(clone);
          pivot.position.set(pose.x, 0, pose.y);
          pivot.rotation.set(0, (-pose.yawDeg * Math.PI) / 180, 0);
          stateRef.current.group.add(pivot);
          stateRef.current.nodes.set(pose.key, pivot);
        })
        .catch((err) => {
          console.warn("[GlbBoardLayer] load failed", pose.url, err);
        });
    });

    return () => {
      cancelled = true;
    };
  }, [poses]);

  return (
    <canvas
      ref={canvasRef}
      className="glb-board-layer"
      aria-hidden
      width={Math.max(1, Math.floor(widthPx))}
      height={Math.max(1, Math.floor(heightPx))}
    />
  );
}
