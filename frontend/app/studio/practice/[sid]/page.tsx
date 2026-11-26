import { Suspense } from "react";

import { AttemptReview } from "@/components/attempt-review";

export const metadata = { title: "Your attempt — AI Dance Teacher" };

export default function AttemptPage() {
  return (
    <Suspense>
      <AttemptReview />
    </Suspense>
  );
}
