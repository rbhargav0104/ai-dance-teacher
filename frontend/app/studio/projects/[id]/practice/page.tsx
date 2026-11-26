import { Suspense } from "react";

import { PracticeStudio } from "@/components/practice-studio";

export const metadata = { title: "Practice — AI Dance Teacher" };

export default function PracticePage() {
  return (
    <Suspense>
      <PracticeStudio />
    </Suspense>
  );
}
