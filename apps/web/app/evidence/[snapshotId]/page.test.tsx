import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./page";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("evidence page", () => {
  it("renders job evidence and safe source link", async () => {
    vi.stubEnv("API_URL", "https://api.example.test");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          job: {
            title: "Backend Engineer",
            company: "Example",
            location: null,
            observed_at: "2026-09-20T00:00:00Z",
          },
          description: "Build evidence-backed APIs.",
          source_url: "https://example.test/jobs/1",
          raw_record_hash: "a".repeat(64),
        }),
      }),
    );

    render(
      await EvidencePage({
        params: Promise.resolve({ snapshotId: "snapshot-1" }),
        searchParams: Promise.resolve({ snapshot: "corpus-1" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "Backend Engineer" })).toBeInTheDocument();
    expect(screen.getByText(/Example/)).toHaveTextContent("Unknown location");
    expect(screen.getByText("Build evidence-backed APIs.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open original source" })).toHaveAttribute(
      "href",
      "https://example.test/jobs/1",
    );
  });

  it("renders explicit unavailable state when evidence request fails", async () => {
    vi.stubEnv("API_URL", "https://api.example.test");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));

    render(
      await EvidencePage({
        params: Promise.resolve({ snapshotId: "missing" }),
        searchParams: Promise.resolve({ snapshot: "corpus-1" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "Evidence unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Job snapshot could not be loaded.")).toBeInTheDocument();
  });
});
