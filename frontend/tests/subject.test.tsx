import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SubjectPicker } from "@/components/subject-picker";
import { cropStyle, cropWindow, followingSummary, padBox, personLabel } from "@/lib/subject";
import type { SubjectInfo } from "@/lib/types";

const subject = (over: Partial<SubjectInfo> = {}): SubjectInfo => ({
  version: "people-1",
  frame_time: 3.9,
  has_frame: true,
  candidates: [
    { person: 1, box: [0.1, 0.2, 0.4, 1], root: [0.3, 0.8], position: "left", share: 1 },
    { person: 2, box: [0.55, 0.1, 0.9, 1], root: [0.7, 0.7], position: "right", share: 0.89 },
  ],
  choice: null,
  followed: null,
  ...over,
});

describe("subject helpers", () => {
  it("pads boxes within the frame", () => {
    expect(padBox([0, 0, 1, 1])).toEqual([0, 0, 1, 1]);
    const [x0, y0, x1, y1] = padBox([0.4, 0.4, 0.6, 0.6], 0.1);
    expect(x0).toBeCloseTo(0.38);
    expect(y1).toBeCloseTo(0.62);
    expect(x1 - x0).toBeCloseTo(0.24);
    expect(y0).toBeCloseTo(0.38);
  });

  it("crops every person to the same 3:4 window that contains their box", () => {
    const aspect = 16 / 9;
    for (const box of [
      [0.25, 0, 0.5, 1],
      [0.1, 0.2, 0.4, 0.9],
      [0.8, 0.3, 0.98, 0.6],
    ] as [number, number, number, number][]) {
      const [x0, y0, x1, y1] = cropWindow(box, aspect);
      expect(((x1 - x0) * aspect) / (y1 - y0)).toBeCloseTo(0.75, 5);
      expect(x0).toBeGreaterThanOrEqual(0);
      expect(y0).toBeGreaterThanOrEqual(0);
      expect(x1).toBeLessThanOrEqual(1 + 1e-9);
      expect(y1).toBeLessThanOrEqual(1 + 1e-9);
      const [px0, py0, px1, py1] = padBox(box);
      if (y1 - y0 < 0.999) {
        expect(px0).toBeGreaterThanOrEqual(x0 - 1e-9);
        expect(px1).toBeLessThanOrEqual(x1 + 1e-9);
        expect(py0).toBeGreaterThanOrEqual(y0 - 1e-9);
        expect(py1).toBeLessThanOrEqual(y1 + 1e-9);
      }
    }
    const s = cropStyle([0.25, 0, 0.5, 1], aspect, "/f.jpg");
    expect(s.backgroundImage).toBe('url("/f.jpg")');
    expect(s.aspectRatio).toBe("3 / 4");
  });

  it("describes whom we follow, honestly about gaps", () => {
    expect(followingSummary(subject())).toBeNull();
    const chosen = subject({ choice: { person: 1, position: "left", t: 3.9, box: [0.1, 0.2, 0.4, 1] } });
    expect(followingSummary(chosen)).toBe("Following person 1 (left)");
    expect(
      followingSummary({ ...chosen, followed: { fraction: 1, lost_spans: [], uncertain_spans: [] } }),
    ).toMatch(/whole video/);
    expect(
      followingSummary({ ...chosen, followed: { fraction: 0.7, lost_spans: [[3, 5.5]], uncertain_spans: [] } }),
    ).toMatch(/Lost them in 1 passage; those moments are left out/);
    expect(personLabel({ person: 2, position: "right" })).toBe("person 2 (right)");
  });
});

describe("SubjectPicker", () => {
  it("lists every detected person and sends the chosen one", async () => {
    const onChoose = vi.fn().mockResolvedValue(undefined);
    render(<SubjectPicker subject={subject()} loadFrame={() => Promise.resolve("/frame.jpg")} onChoose={onChoose} />);
    expect(screen.getByRole("heading", { name: "Who should we follow?" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "/frame.jpg"));
    const second = screen.getByRole("button", { name: /Follow person 2 \(right\), in 89%/ });
    fireEvent.click(second);
    await waitFor(() => expect(onChoose).toHaveBeenCalledWith(2));
  });

  it("marks the current choice and shows server errors (e.g. LIMITED)", async () => {
    const onChoose = vi.fn().mockRejectedValue(new Error("Your choice is saved, but movement analysis isn't available"));
    render(
      <SubjectPicker
        subject={subject({ choice: { person: 1, position: "left", t: 3.9, box: [0.1, 0.2, 0.4, 1] } })}
        loadFrame={() => Promise.reject(new Error("gone"))}
        onChoose={onChoose}
      />,
    );
    expect(screen.getByRole("heading", { name: "Follow someone else?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /currently followed/ })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(screen.getByText(/frame couldn't be loaded/)).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subject-person-2"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/choice is saved/));
  });

  it("disables choosing with a reason", () => {
    render(
      <SubjectPicker subject={subject()} loadFrame={() => new Promise(() => {})} onChoose={vi.fn()} disabledReason="Analysis is running." />,
    );
    expect(screen.getByTestId("subject-person-1")).toBeDisabled();
    expect(screen.getByText("Analysis is running.")).toBeInTheDocument();
  });
});
