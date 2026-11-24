import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration, precheckDuration, precheckFile, projectStatusLabel } from "@/lib/media";

const limits = { max_upload_mb: 200, max_duration_seconds: 120, accepted_extensions: [".mp4", ".mov", ".webm"] };

describe("upload prechecks", () => {
  it("accepts supported extensions case-insensitively", () => {
    expect(precheckFile({ name: "Dance.MP4", size: 10 }, limits)).toBeNull();
    expect(precheckFile({ name: "a.webm", size: 10 }, limits)).toBeNull();
  });
  it("rejects other types, empty and oversized files with actionable copy", () => {
    expect(precheckFile({ name: "a.avi", size: 10 }, limits)).toBe("Choose an MP4, MOV or WEBM video.");
    expect(precheckFile({ name: "noext", size: 10 }, limits)).toMatch(/Choose/);
    expect(precheckFile({ name: "a.mp4", size: 0 }, limits)).toBe("This file is empty.");
    expect(precheckFile({ name: "a.mp4", size: 201 * 1024 * 1024 }, limits)).toMatch(/limit is 200 MB/);
  });
  it("flags durations outside 1 s … max", () => {
    expect(precheckDuration(0.5, limits)).toMatch(/shorter than 1 second/);
    expect(precheckDuration(130, limits)).toMatch(/Trim it to 2:00/);
    expect(precheckDuration(null, limits)).toBeNull();
    expect(precheckDuration(Number.NaN, limits)).toBeNull();
    expect(precheckDuration(30, limits)).toBeNull();
  });
});

describe("formatting", () => {
  it("formats bytes and durations", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1_300_654)).toBe("1.2 MB");
    expect(formatDuration(4.2)).toBe("4.2 s");
    expect(formatDuration(14)).toBe("14 s");
    expect(formatDuration(75)).toBe("1:15");
  });
  it("never labels an un-analyzed project as ready", () => {
    expect(projectStatusLabel("uploaded").label).toMatch(/waiting for analysis/);
    expect(projectStatusLabel("uploaded").tone).not.toBe("lime");
  });
});
