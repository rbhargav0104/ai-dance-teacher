import { Suspense } from "react";

import { ProjectView } from "@/components/project-view";

export const metadata = { title: "Dance — AI Dance Teacher" };

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectView />
    </Suspense>
  );
}
