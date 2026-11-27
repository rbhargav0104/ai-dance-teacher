import { Suspense } from "react";

import { AlignmentView } from "@/components/alignment-view";

export const metadata = { title: "Alignment — AI Dance Teacher" };

export default function AlignmentPage() {
  return (
    <Suspense>
      <AlignmentView />
    </Suspense>
  );
}
