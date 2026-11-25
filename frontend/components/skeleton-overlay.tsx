"use client";

import { type RefObject, useEffect, useRef } from "react";

import { containRect, frameAt, jointState, toScreen } from "@/lib/pose";
import type { PoseFrame, PosesResponse } from "@/lib/types";

const LIME = "#c1f86a";
const TRACK = "#9bea35";
const TRAIL_JOINTS = [15, 16, 27, 28]; // wrists + ankles leave a short movement trail

export interface OverlayOptions {
  showIds?: boolean;
  trails?: boolean;
  highlight?: number | null;
}

/**
 * Draws the measured skeleton over a <video>, synced to its current time. Only landmarks
 * MediaPipe actually measured are drawn; bridged (interpolated) joints are faint and dashed.
 */
export function SkeletonOverlay({
  videoRef,
  poses,
  options = {},
  onFrame,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  poses: PosesResponse;
  options?: OverlayOptions;
  onFrame?: (frame: PoseFrame | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const optsRef = useRef(options);
  const onFrameRef = useRef(onFrame);
  const kickRef = useRef<() => void>(() => {});
  useEffect(() => {
    optsRef.current = options;
    onFrameRef.current = onFrame;
    kickRef.current();
  });

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const fps = poses.analysis_fps ?? 12;
    const mediaW = poses.width ?? video.videoWidth;
    const mediaH = poses.height ?? video.videoHeight;
    let raf = 0;
    let lastFrame: PoseFrame | null | undefined;

    const draw = () => {
      const box = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.round(box.width * dpr);
      const h = Math.round(box.height * dpr);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, box.width, box.height);
      const t = video.currentTime;
      const frame = frameAt(poses.frames, t, fps);
      if (frame !== lastFrame) {
        lastFrame = frame;
        onFrameRef.current?.(frame);
      }
      if (!frame) return;
      const rect = containRect(box.width, box.height, mediaW, mediaH);
      const opts = optsRef.current;
      const pts = frame.data.smoothed;

      if (opts.trails !== false) {
        const idx = poses.frames.indexOf(frame);
        for (const j of TRAIL_JOINTS) {
          ctx.beginPath();
          let started = false;
          for (let k = Math.max(0, idx - 6); k <= idx; k++) {
            const f = poses.frames[k];
            const p = f.data.smoothed[j];
            if (!p || !f.data.reliable[j]) {
              started = false;
              continue;
            }
            const [x, y] = toScreen(rect, p[0], p[1]);
            if (started) ctx.lineTo(x, y);
            else ctx.moveTo(x, y);
            started = true;
          }
          ctx.strokeStyle = "rgba(193, 248, 106, 0.28)";
          ctx.lineWidth = 6;
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          ctx.stroke();
        }
      }

      for (const [a, b] of poses.connections) {
        const sa = jointState(frame, a);
        const sb = jointState(frame, b);
        if (sa === "hidden" || sb === "hidden") continue;
        const pa = pts[a]!;
        const pb = pts[b]!;
        const [x1, y1] = toScreen(rect, pa[0], pa[1]);
        const [x2, y2] = toScreen(rect, pb[0], pb[1]);
        const bridged = sa === "bridged" || sb === "bridged";
        ctx.setLineDash(bridged ? [4, 5] : []);
        ctx.strokeStyle = bridged ? "rgba(193, 248, 106, 0.4)" : frame.valid ? LIME : "rgba(245, 184, 75, 0.85)";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      ctx.font = "600 10px ui-monospace, monospace";
      for (let j = 0; j < pts.length; j++) {
        const s = jointState(frame, j);
        if (s === "hidden") continue;
        const p = pts[j]!;
        const [x, y] = toScreen(rect, p[0], p[1]);
        const hi = opts.highlight === j;
        ctx.beginPath();
        ctx.arc(x, y, hi ? 7 : j < 11 ? 2.5 : 4, 0, Math.PI * 2);
        ctx.fillStyle = s === "bridged" ? "rgba(16, 18, 15, 0.7)" : hi ? "#ffffff" : TRACK;
        ctx.fill();
        ctx.strokeStyle = "#10120f";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        if (opts.showIds && (j >= 11 || j === 0)) {
          ctx.fillStyle = "rgba(16, 18, 15, 0.8)";
          ctx.fillRect(x + 6, y - 7, j > 9 ? 17 : 11, 13);
          ctx.fillStyle = LIME;
          ctx.fillText(String(j), x + 8, y + 3);
        }
      }
    };

    const loop = () => {
      draw();
      raf = video.paused || video.ended ? 0 : requestAnimationFrame(loop);
    };
    const kick = () => {
      if (!raf) raf = requestAnimationFrame(loop);
    };
    const events = ["play", "seeked", "timeupdate", "loadeddata", "ratechange"] as const;
    events.forEach((e) => video.addEventListener(e, kick));
    const ro = new ResizeObserver(kick);
    ro.observe(canvas);
    kickRef.current = kick;
    kick();
    return () => {
      kickRef.current = () => {};
      cancelAnimationFrame(raf);
      events.forEach((e) => video.removeEventListener(e, kick));
      ro.disconnect();
    };
  }, [videoRef, poses]);

  return <canvas ref={canvasRef} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />;
}
