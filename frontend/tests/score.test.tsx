import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScoreCard, clockTenths } from "@/components/score-card";
import * as api from "@/lib/api";
import { evidenceText, hasNumbers, qualifierText, scoreText, scoreTone, sectionExtremes, weightText } from "@/lib/score";
import type { ScoreReport, SectionScore } from "@/lib/types";

const report = (over: Partial<ScoreReport> = {}): ScoreReport => ({
  version: "score-1",
  alignment_version: "align-1",
  status: "scored",
  overall: 84.4,
  components: { pose: 88.2, timing: 76.0, sequence: 91.0, joint_angles: 80.0, rhythm: null },
  weights: { pose: 0.3, timing: 0.25, sequence: 0.2, joint_angles: 0.15, rhythm: 0.1 },
  weights_used: { pose: 0.3333, timing: 0.2778, sequence: 0.2222, joint_angles: 0.1667 },
  warnings: ["rhythm_unavailable:too_short", "compared_mirrored"],
  coverage: {
    reference_tracking: 0.9,
    learner_tracking: 0.85,
    compared_frames: 120,
    reference_frames: 144,
    visible_joint_coverage: 0.97,
    masked_fraction: 0.1,
    alignment_confidence: 0.86,
    warp: 0.1,
    confidence: 0.83,
  },
  evidence: {
    pose: { mean_joint_distance_torso: 0.041, mean_lean_difference_deg: 2.4, pairs: 120 },
    joint_angles: { focused_angle_error_deg: 12.6, pairs: 120 },
    timing: { median_offset_s: 0.42, mean_abs_offset_s: 0.44, on_time_share: 0.1, tolerance_s: 0.12 },
    sequence: { matched_share: 0.8, missing_share: 0.2, held_share: 0, mean_direction_disagreement: 0.1, non_diagonal_fraction: 0.05 },
    rhythm: { unavailable: "too_short" },
  },
  moments: {
    worst: [{ ref_t: 10.3, learner_t: 10.7, pose_value: 70, joint_distance_torso: 0.19, largest_differences: ["left_arm", "torso"] }],
    best: { ref_t: 1.5, learner_t: 1.9, pose_value: 99.9, joint_distance_torso: 0.01, largest_differences: [] },
  },
  sections: [
    { id: "a", title: "Section 1", start: 0, end: 6.9, compared_pairs: 70, status: "scored", overall: 90, components: null },
    { id: "b", title: "Section 2", start: 6.9, end: 14, compared_pairs: 50, status: "scored", overall: 71, components: null },
  ],
  ...over,
});

afterEach(() => vi.restoreAllMocks());

describe("score helpers", () => {
  it("formats without inventing numbers", () => {
    expect(scoreText(84.6)).toBe("85");
    expect(scoreText(null)).toBe("—");
    expect(scoreText(Number.NaN)).toBe("—");
    expect(scoreTone(90)).toBe("lime");
    expect(scoreTone(72)).toBe("track");
    expect(scoreTone(55)).toBe("amber");
    expect(scoreTone(20)).toBe("danger");
  });

  it("shows numbers only for scored/qualified reports with an overall", () => {
    expect(hasNumbers(report())).toBe(true);
    expect(hasNumbers(report({ status: "qualified" }))).toBe(true);
    expect(hasNumbers(report({ status: "suppressed", overall: null }))).toBe(false);
    expect(hasNumbers(report({ status: "not_scored", overall: null }))).toBe(false);
  });

  it("words the measured evidence", () => {
    const r = report();
    expect(evidenceText(r, "timing")).toContain("0.42 s late");
    expect(evidenceText(report({ evidence: { timing: { median_offset_s: -0.3, mean_abs_offset_s: 0.3, on_time_share: 0.2, tolerance_s: 0.12 } } }), "timing")).toContain("0.30 s early");
    expect(evidenceText(report({ evidence: { timing: { median_offset_s: 0.05, mean_abs_offset_s: 0.05, on_time_share: 1, tolerance_s: 0.12 } } }), "timing")).toContain("on time");
    expect(evidenceText(r, "pose")).toContain("4% of a torso length");
    expect(evidenceText(r, "sequence")).toContain("80% of the reference's measured moves matched · 20% missed");
    expect(evidenceText(r, "joint_angles")).toContain("13°");
    expect(evidenceText(r, "rhythm")).toContain("Too short");
  });

  it("reports the re-normalised weight or 'not counted'", () => {
    expect(weightText(report(), "pose")).toBe("33% of overall");
    expect(weightText(report(), "rhythm")).toBe("not counted");
  });

  it("finds strongest/weakest sections only when two are scored", () => {
    const ex = sectionExtremes(report().sections);
    expect(ex?.strongest.id).toBe("a");
    expect(ex?.weakest.id).toBe("b");
    const one: SectionScore[] = [report().sections![0], { ...report().sections![1], status: "insufficient", overall: null }];
    expect(sectionExtremes(one)).toBeNull();
    expect(sectionExtremes([])).toBeNull();
  });

  it("shows moment clocks with tenths", () => {
    expect(clockTenths(0.33)).toBe("0:00.3");
    expect(clockTenths(0.92)).toBe("0:00.9");
    expect(clockTenths(65.04)).toBe("1:05.0");
  });

  it("explains qualifiers", () => {
    expect(qualifierText(report({ status: "qualified", qualifiers: ["low_confidence"] }))).toContain("uncertain");
    expect(qualifierText(report())).toBeNull();
  });
});

describe("ScoreCard", () => {
  it("renders the overall, components, coverage, sections and replay moments", async () => {
    vi.spyOn(api, "getPracticeReport").mockResolvedValue({ practice_id: "p", cached: true, report: report() });
    const onSeek = vi.fn();
    render(<ScoreCard attemptId="p" onSeek={onSeek} />);
    await waitFor(() => expect(screen.getByTestId("score-overall")).toHaveTextContent("84/ 100"));
    expect(screen.getByTestId("score-rhythm")).toHaveTextContent("not counted");
    expect(screen.getByTestId("score-rhythm")).toHaveTextContent("—");
    expect(screen.getByTestId("score-coverage")).toHaveTextContent("120/144");
    expect(screen.getByTestId("score-sections")).toHaveTextContent("weakest");
    expect(screen.getByTestId("score-warnings")).toHaveTextContent("mirror image");
    const moments = screen.getAllByTestId("score-moment");
    expect(moments[0]).toHaveTextContent("left arm and torso");
    fireEvent.click(moments[0]);
    expect(onSeek).toHaveBeenCalledWith(10.7);
  });

  it("withholds every number when the score is suppressed", async () => {
    const r = report({
      status: "suppressed",
      overall: null,
      components: { pose: null, timing: null, sequence: null, joint_angles: null, rhythm: null },
      weights_used: {},
      message: "Too few moments could be compared to give a fair score.",
    });
    vi.spyOn(api, "getPracticeReport").mockResolvedValue({ practice_id: "p", cached: false, report: r });
    render(<ScoreCard attemptId="p" onSeek={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("score-withheld")).toHaveTextContent("Too few moments"));
    expect(screen.queryByTestId("score-overall")).toBeNull();
    expect(screen.queryByTestId("score-moments")).toBeNull();
    for (const k of ["pose", "timing", "sequence", "joint_angles", "rhythm"]) {
      expect(screen.getByTestId(`score-${k}`)).toHaveTextContent("—");
      expect(screen.getByTestId(`score-${k}`)).toHaveTextContent("withheld");
    }
    expect(screen.getByTestId("score-card")).toHaveAttribute("data-status", "suppressed");
  });

  it("says scoring is off instead of estimating when the server can't score", async () => {
    vi.spyOn(api, "getPracticeReport").mockRejectedValue(new api.ApiError(503, "analysis_unavailable", "Scoring isn't available on this server."));
    render(<ScoreCard attemptId="p" onSeek={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("score-error")).toHaveTextContent("won't estimate"));
  });
});
