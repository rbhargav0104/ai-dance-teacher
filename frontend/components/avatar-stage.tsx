"use client";
/* eslint-disable react-hooks/immutability -- three.js materials/vectors are mutated per frame inside useFrame by design (R3F pattern); React never renders from them. */

/**
 * 3D teacher stage (spec amendment A1): an original procedural mannequin driven only by this
 * video's measured world landmarks (via lib/avatar/track.ts). The video element is the clock;
 * every rendered frame samples the track at `video.currentTime`.
 *
 * Honesty: bones not measured in a frame are held at rest and drawn ghosted; bones bridged over
 * a ≤ 2-frame gap are drawn faint; when the nearest analysed frame has no usable pose the stage
 * says "tracking lost here" and fades the body instead of freezing or guessing.
 */

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Component, type ReactNode, type RefObject, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import { BONES, type BoneName, type BoneState } from "@/lib/avatar/retarget";
import type { CameraView } from "@/lib/avatar/stage-config";
import { type AvatarTrack, type SampleStatus, sampleTrack, untrackedParts } from "@/lib/avatar/track";

const TARGET = new THREE.Vector3(0, 0.98, 0);
const CAMERA_POS: Record<CameraView, THREE.Vector3> = {
  front: new THREE.Vector3(0, 1.12, 3.15),
  "three-quarter": new THREE.Vector3(2.2, 1.3, 2.3),
  side: new THREE.Vector3(3.15, 1.12, 0.01),
};

const COLORS = {
  body: "#e9ecdf",
  lime: "#c1f86a",
  ghost: "#8a917f",
  floor: "#171a15",
  bg: "#10120f",
};

/** Debug snapshot of what was actually rendered (read by the Playwright avatar check). */
export interface AvatarDebug {
  t: number;
  status: SampleStatus;
  mirrored: boolean;
  bones: Partial<Record<BoneName, { dir: [number, number, number]; state: BoneState }>>;
  frames: number;
}

declare global {
  interface Window {
    __adtAvatar?: AvatarDebug;
  }
}

class StageBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function AvatarStage({
  track,
  videoRef,
  view,
  reducedMotion,
  compact = false,
  onStatus,
  fallback,
}: {
  track: AvatarTrack;
  videoRef: RefObject<HTMLVideoElement | null>;
  view: CameraView;
  reducedMotion: boolean;
  compact?: boolean;
  onStatus?: (s: SampleStatus) => void;
  fallback: ReactNode;
}) {
  const [status, setStatus] = useState<SampleStatus>("tracked");
  const parts = useMemo(() => untrackedParts(track.rig), [track]);
  const report = (s: SampleStatus) => {
    setStatus(s);
    onStatus?.(s);
  };

  return (
    <StageBoundary fallback={fallback}>
      <div className="absolute inset-0" data-testid="avatar-stage" data-status={status} data-mirrored={track.mirrored}>
        <Canvas
          camera={{ position: CAMERA_POS[view].toArray(), fov: 34, near: 0.05, far: 40 }}
          dpr={[1, 2]}
          gl={{ antialias: true, preserveDrawingBuffer: true }}
          shadows
          aria-label="3D avatar performing the measured movement"
        >
          <color attach="background" args={[COLORS.bg]} />
          <fog attach="fog" args={[COLORS.bg, 6, 13]} />
          <hemisphereLight args={["#f3f7e8", "#0c0e0b", 0.75]} />
          <directionalLight position={[2.5, 4.5, 3.5]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]} />
          <directionalLight position={[-3, 2.5, -2]} intensity={0.55} color={COLORS.lime} />
          <Floor />
          <Mannequin track={track} videoRef={videoRef} onStatus={report} />
          <CameraRig view={view} reducedMotion={reducedMotion} />
        </Canvas>

        {!compact && parts.length > 0 && (
          <p
            className="pointer-events-none absolute bottom-14 left-3 max-w-[85%] rounded-full sm:bottom-auto sm:max-w-[70%] border border-amber/40 bg-studio/80 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-amber backdrop-blur sm:left-4 sm:top-4"
            data-testid="avatar-untracked"
          >
            Not tracked in this video: {parts.join(", ")} · shown ghosted
          </p>
        )}
        {status === "lost" && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center" data-testid="avatar-lost">
            <p className="rounded-2xl border border-amber/50 bg-studio/85 px-4 py-2 text-center text-sm text-amber backdrop-blur">
              Tracking lost here
              {!compact && <span className="block text-xs text-muted">The dancer wasn&apos;t measured at this moment. Watch the video.</span>}
            </p>
          </div>
        )}
      </div>
    </StageBoundary>
  );
}

function Floor() {
  const ring = useMemo(() => new THREE.RingGeometry(0.62, 0.64, 96), []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow>
        <circleGeometry args={[3.2, 96]} />
        <meshStandardMaterial color={COLORS.floor} roughness={0.95} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.002} geometry={ring}>
        <meshBasicMaterial color={COLORS.lime} transparent opacity={0.55} />
      </mesh>
      <gridHelper args={[6.4, 16, "#2a2f26", "#20241d"]} position-y={0.001} />
    </group>
  );
}

function CameraRig({ view, reducedMotion }: { view: CameraView; reducedMotion: boolean }) {
  const controls = useRef<OrbitControlsImpl | null>(null);
  const camera = useThree((s) => s.camera);
  const goal = useRef<THREE.Vector3 | null>(null);

  useEffect(() => {
    const to = CAMERA_POS[view].clone();
    if (reducedMotion) {
      camera.position.copy(to);
      controls.current?.target.copy(TARGET);
      controls.current?.update();
      goal.current = null;
    } else {
      goal.current = to;
    }
  }, [view, reducedMotion, camera]);

  useFrame((_, dt) => {
    if (!goal.current) return;
    const k = 1 - Math.exp(-dt * 6);
    camera.position.lerp(goal.current, k);
    controls.current?.target.lerp(TARGET, k);
    controls.current?.update();
    if (camera.position.distanceTo(goal.current) < 0.01) goal.current = null;
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      target={TARGET.toArray()}
      enablePan={false}
      minDistance={1.6}
      maxDistance={7}
      minPolarAngle={0.2}
      maxPolarAngle={Math.PI / 2 - 0.04}
      onStart={() => (goal.current = null)}
    />
  );
}

const Y = new THREE.Vector3(0, 1, 0);
const JOINT_KEYS = ["shoulderL", "shoulderR", "elbowL", "elbowR", "wristL", "wristR", "hipL", "hipR", "kneeL", "kneeR", "ankleL", "ankleR"] as const;
type JointKey = (typeof JOINT_KEYS)[number];
/** Which bone end each joint sits on, and which bone's state colours it. */
const JOINT_OF: Record<JointKey, { bone: BoneName; end: "start" | "end" }> = {
  shoulderL: { bone: "upperArmL", end: "start" },
  shoulderR: { bone: "upperArmR", end: "start" },
  elbowL: { bone: "upperArmL", end: "end" },
  elbowR: { bone: "upperArmR", end: "end" },
  wristL: { bone: "forearmL", end: "end" },
  wristR: { bone: "forearmR", end: "end" },
  hipL: { bone: "thighL", end: "start" },
  hipR: { bone: "thighR", end: "start" },
  kneeL: { bone: "thighL", end: "end" },
  kneeR: { bone: "thighR", end: "end" },
  ankleL: { bone: "shinL", end: "end" },
  ankleR: { bone: "shinR", end: "end" },
};

const RADIUS: Record<BoneName, number> = {
  spine: 0.05,
  neck: 0.045,
  upperArmL: 0.05,
  upperArmR: 0.05,
  forearmL: 0.042,
  forearmR: 0.042,
  thighL: 0.07,
  thighR: 0.07,
  shinL: 0.055,
  shinR: 0.055,
};

function opacityFor(state: BoneState, lost: boolean): number {
  if (lost) return 0.14;
  return state === "measured" ? 1 : state === "bridged" ? 0.5 : 0.16;
}

function Mannequin({
  track,
  videoRef,
  onStatus,
}: {
  track: AvatarTrack;
  videoRef: RefObject<HTMLVideoElement | null>;
  onStatus: (s: SampleStatus) => void;
}) {
  const { rig } = track;
  const lift = track.legLength + 0.08;
  const boneMeshes = useRef<Partial<Record<BoneName, THREE.Mesh>>>({});
  const jointMeshes = useRef<Partial<Record<JointKey, THREE.Mesh>>>({});
  const torso = useRef<THREE.Mesh | null>(null);
  const head = useRef<THREE.Mesh | null>(null);
  const pelvis = useRef<THREE.Mesh | null>(null);
  const lastStatus = useRef<SampleStatus | null>(null);
  const frames = useRef(0);

  const geoms = useMemo(() => {
    const g = {} as Record<BoneName, THREE.CapsuleGeometry>;
    for (const b of BONES) g[b.name] = new THREE.CapsuleGeometry(RADIUS[b.name], Math.max(0.01, rig.lengths[b.name] - RADIUS[b.name] * 2), 6, 14);
    return g;
  }, [rig]);
  const torsoGeom = useMemo(() => {
    const top = Math.max(0.09, rig.shoulderWidth * 0.42);
    const bottom = Math.max(0.08, rig.hipWidth * 0.5);
    return new THREE.CylinderGeometry(top, bottom, rig.lengths.spine * 0.92, 24, 1);
  }, [rig]);

  const mats = useMemo(() => {
    const body = (color: string) => new THREE.MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.05, transparent: true });
    const m = {} as Record<BoneName, THREE.MeshStandardMaterial>;
    for (const b of BONES) m[b.name] = body(COLORS.body);
    const joints = {} as Record<JointKey, THREE.MeshStandardMaterial>;
    for (const j of JOINT_KEYS)
      joints[j] = new THREE.MeshStandardMaterial({ color: COLORS.lime, emissive: COLORS.lime, emissiveIntensity: 0.35, roughness: 0.3, transparent: true });
    return { bones: m, joints, torso: body(COLORS.body), head: body(COLORS.body) };
  }, []);

  useEffect(
    () => () => {
      Object.values(geoms).forEach((g) => g.dispose());
      torsoGeom.dispose();
    },
    [geoms, torsoGeom],
  );

  const tmp = useMemo(
    () => ({ v: new THREE.Vector3(), a: new THREE.Vector3(), b: new THREE.Vector3(), x: new THREE.Vector3(), z: new THREE.Vector3(), m: new THREE.Matrix4() }),
    [],
  );

  useFrame(() => {
    const video = videoRef.current;
    const t = video ? video.currentTime : 0;
    const sample = sampleTrack(track, t);
    const lost = sample.status !== "tracked";
    if (lastStatus.current !== sample.status) {
      lastStatus.current = sample.status;
      onStatus(sample.status);
    }
    // Rest pose (never the last known pose) whenever the moment is unknown.
    const pose = !lost && sample.pose ? sample.pose : track.rest;
    const debug: AvatarDebug = { t, status: sample.status, mirrored: track.mirrored, bones: {}, frames: ++frames.current };

    for (const def of BONES) {
      const bone = pose.bones[def.name];
      const mesh = boneMeshes.current[def.name];
      if (!mesh) continue;
      const state = bone.state;
      const dir = bone.dir;
      tmp.v.set(dir[0], dir[1], dir[2]).normalize();
      mesh.quaternion.setFromUnitVectors(Y, tmp.v);
      tmp.a.set(bone.start[0], bone.start[1], bone.start[2]);
      mesh.position.copy(tmp.a).addScaledVector(tmp.v, rig.lengths[def.name] / 2);
      const mat = mats.bones[def.name];
      mat.opacity = opacityFor(state, lost);
      mat.color.set(state === "untracked" ? COLORS.ghost : COLORS.body);
      mat.depthWrite = state === "measured";
      mesh.castShadow = state === "measured";
      const rendered = new THREE.Vector3(0, 1, 0).applyQuaternion(mesh.quaternion);
      debug.bones[def.name] = { dir: [rendered.x, rendered.y, rendered.z], state };
    }

    for (const key of JOINT_KEYS) {
      const mesh = jointMeshes.current[key];
      if (!mesh) continue;
      const { bone, end } = JOINT_OF[key];
      const b = pose.bones[bone];
      const p = end === "start" ? b.start : b.end;
      mesh.position.set(p[0], p[1], p[2]);
      const state = b.state;
      const mat = mats.joints[key];
      mat.opacity = opacityFor(state, lost);
      mat.color.set(state === "untracked" ? COLORS.ghost : COLORS.lime);
      mat.emissiveIntensity = state === "measured" ? 0.35 : 0;
    }
    const spine = pose.bones.spine;
    const spineDir = spine.dir;
    if (torso.current) {
      tmp.v.set(spineDir[0], spineDir[1], spineDir[2]).normalize();
      const axis = pose.shoulderAxis ?? ([1, 0, 0] as const);
      tmp.x.set(axis[0], axis[1], axis[2]);
      tmp.x.addScaledVector(tmp.v, -tmp.x.dot(tmp.v)).normalize();
      if (tmp.x.lengthSq() < 1e-6) tmp.x.set(1, 0, 0);
      tmp.z.crossVectors(tmp.x, tmp.v).normalize();
      tmp.m.makeBasis(tmp.x, tmp.v, tmp.z);
      torso.current.quaternion.setFromRotationMatrix(tmp.m);
      torso.current.scale.set(1, 1, 0.55);
      torso.current.position.set(spineDir[0] * rig.lengths.spine * 0.5, spineDir[1] * rig.lengths.spine * 0.5, spineDir[2] * rig.lengths.spine * 0.5);
      if (pelvis.current) {
        // Pelvis follows the torso's orientation; drawn ghosted with it when the hips weren't measured.
        pelvis.current.quaternion.copy(torso.current.quaternion);
        pelvis.current.position.set(0, 0, 0);
        pelvis.current.scale.set(Math.max(0.1, rig.hipWidth * 0.62), 0.11, 0.1);
      }
      const st = spine.state;
      mats.torso.opacity = opacityFor(st, lost);
      mats.torso.color.set(st === "untracked" ? COLORS.ghost : COLORS.body);
    }
    if (head.current) {
      const neck = pose.bones.neck;
      const d = neck.dir;
      const base = neck.start;
      const L = rig.lengths.neck;
      head.current.position.set(base[0] + d[0] * L * 0.95, base[1] + d[1] * L * 0.95, base[2] + d[2] * L * 0.95);
      const st = neck.state;
      mats.head.opacity = opacityFor(st, lost);
      mats.head.color.set(st === "untracked" ? COLORS.ghost : COLORS.body);
    }
    if (typeof window !== "undefined") window.__adtAvatar = debug;
  });

  return (
    <group position-y={lift}>
      <mesh ref={torso} geometry={torsoGeom} material={mats.torso} castShadow />
      <mesh ref={pelvis} material={mats.torso} castShadow>
        <sphereGeometry args={[1, 24, 16]} />
      </mesh>
      <mesh ref={head} material={mats.head} castShadow>
        <sphereGeometry args={[0.105, 24, 18]} />
      </mesh>
      {BONES.filter((b) => b.name !== "spine" && b.name !== "neck").map((b) => (
        <mesh
          key={b.name}
          ref={(m) => {
            boneMeshes.current[b.name] = m ?? undefined;
          }}
          geometry={geoms[b.name]}
          material={mats.bones[b.name]}
        />
      ))}
      {/* Spine and neck are posed (for the debug check) but drawn by the torso and head. */}
      {(["spine", "neck"] as const).map((n) => (
        <mesh
          key={n}
          visible={false}
          ref={(m) => {
            boneMeshes.current[n] = m ?? undefined;
          }}
          geometry={geoms[n]}
        />
      ))}
      {JOINT_KEYS.map((k) => (
        <mesh
          key={k}
          ref={(m) => {
            jointMeshes.current[k] = m ?? undefined;
          }}
          material={mats.joints[k]}
        >
          <sphereGeometry args={[k.startsWith("wrist") || k.startsWith("ankle") ? 0.045 : 0.055, 16, 12]} />
        </mesh>
      ))}
    </group>
  );
}
