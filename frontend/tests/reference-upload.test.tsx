import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReferenceUpload } from "@/components/reference-upload";

const limits = { max_upload_mb: 1, max_duration_seconds: 120, accepted_extensions: [".mp4", ".mov", ".webm"] };

function pick(file: File) {
  const input = screen.getByLabelText(/drop a dance video/i, { selector: "input" });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("ReferenceUpload", () => {
  it("rejects unsupported files before uploading, with an accessible alert", () => {
    render(<ReferenceUpload limits={limits} disabledReason={null} onUploaded={vi.fn()} />);
    pick(new File(["x"], "notes.txt", { type: "text/plain" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/MP4, MOV or WEBM/);
    expect(screen.queryByRole("button", { name: /upload to studio/i })).toBeNull();
  });

  it("shows the selected file with remove/reselect before submission", () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
    render(<ReferenceUpload limits={limits} disabledReason={null} onUploaded={vi.fn()} />);
    pick(new File([new Uint8Array(2048)], "combo.mp4", { type: "video/mp4" }));
    expect(screen.getByText("combo.mp4")).toBeInTheDocument();
    expect(screen.getByText("2 KB")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByText("combo.mp4")).toBeNull();
    expect(screen.getByText(/drop a dance video here/i)).toBeInTheDocument();
  });

  it("explains why upload is disabled when the server can't inspect video", () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    render(<ReferenceUpload limits={limits} disabledReason="Video inspection isn't available." onUploaded={vi.fn()} />);
    pick(new File([new Uint8Array(10)], "combo.mp4", { type: "video/mp4" }));
    expect(screen.getByRole("button", { name: /upload to studio/i })).toBeDisabled();
    expect(screen.getByText(/inspection isn't available/)).toBeInTheDocument();
  });
});
