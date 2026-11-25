import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisFailure, AnalysisProgress, TrackingSummary } from "@/components/analysis-status";
import type { Project } from "@/lib/types";

function project(over: Partial<Project> = {}): Project {
  return {
    id: "p1",
    title: "t",
    status: "uploaded",
    progress: 0,
    is_demo: false,
    error_code: null,
    error_message: null,
    created_at: "",
    updated_at: "",
    reference: null,
    latest_job: null,
    ...over,
  };
}

describe("analysis status", () => {
  it("shows the worker's real stage and progress while running", () => {
    render(
      <AnalysisProgress
        project={project({
          status: "processing",
          latest_job: { id: "j", kind: "reference_analysis", status: "running", stage: "tracking", progress: 0.42, message: null, error_code: null, updated_at: "" },
        })}
      />,
    );
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText(/tracking the body/i)).toBeInTheDocument();
  });

  it("renders nothing when idle", () => {
    const { container } = render(<AnalysisProgress project={project()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the server's actionable failure message", () => {
    render(<AnalysisFailure project={project({ status: "failed", error_code: "multiple_people", error_message: "More than one person appears." })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("More than one person appears.");
  });

  it("labels tracking confidence as not a dance score", () => {
    render(
      <TrackingSummary
        project={project({
          status: "analyzed",
          reference: {
            original_filename: null, duration: 14, width: 1280, height: 720, source_fps: 24, size_bytes: 1, codec: "h264", has_audio: false, warnings: [],
            quality: { analyzed_frames: 168, valid_frames: 149, coverage: 0.887, multi_person_fraction: 0, feet_visible_fraction: 0, mean_confidence: 0.6, measured_joint_confidence: 0.95, interpolated_frames: 6, failure: null, failure_message: null, warnings: [], excluded_joints: {} },
          },
        })}
      />,
    );
    expect(screen.getByText("89%")).toBeInTheDocument();
    expect(screen.getByText("149/168")).toBeInTheDocument();
    expect(screen.getByTitle(/not a dance score/i)).toBeInTheDocument();
  });
});
