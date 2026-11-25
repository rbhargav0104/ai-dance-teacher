import { Suspense } from "react";

import { PoseDebugger } from "@/components/pose-debugger";

export const metadata = { title: "Pose debugger — AI Dance Teacher" };

export default function DebugPage() {
  return (
    <Suspense>
      <PoseDebugger />
    </Suspense>
  );
}
