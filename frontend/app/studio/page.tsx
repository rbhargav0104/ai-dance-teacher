import { Suspense } from "react";

import { StudioShell } from "@/components/studio-shell";

export const metadata = { title: "Studio — AI Dance Teacher" };

export default function StudioPage() {
  return (
    <Suspense>
      <StudioShell />
    </Suspense>
  );
}
