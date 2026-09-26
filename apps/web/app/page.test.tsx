import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadDashboard } from "../lib/market";
import Dashboard, { ErrorState } from "./page";

vi.mock("../lib/market", () => ({ loadDashboard: vi.fn() }));
const mockedLoad = vi.mocked(loadDashboard);
const params = Promise.resolve({});

beforeEach(() => mockedLoad.mockReset());
afterEach(() => cleanup());

describe("dashboard", () => {
  it("renders explicit empty state and coverage qualification", async () => {
    mockedLoad.mockResolvedValue(null);
    render(await Dashboard({ searchParams: params }));
    expect(screen.getByRole("heading", { name: "Market evidence" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No published snapshot");
    expect(screen.getByText(/not whole labor market/i)).toBeInTheDocument();
  });

  it("renders explicit API error state", () => {
    render(<ErrorState />);
    expect(screen.getByRole("alert")).toHaveTextContent("Market data unavailable");
  });

  it("renders all M3 workflows, labels, evidence, unknowns, and pagination", async () => {
    const statistic = { id: "stat-1", value: "0.5", numerator: 1, denominator: 2, unit: "ratio", dimensions: { skill: "python", role: "unknown", left_role: "backend_engineer", right_role: "data_engineer" }, cutoff: "2026-09-20T00:00:00Z", snapshot: "corpus-1", versions: { metric: "v1", taxonomy: "t1", normalization: "n1", extraction: "e1" }, warning: "Small sample", evidence: ["snapshot-1"], metadata: { left_numerator: 1, right_numerator: 0, left_denominator: 1, right_denominator: 1 } };
    const page = { analytics_run_id: "run-1", data: [statistic], page: { has_more: true, next_cursor: "next-1" } };
    mockedLoad.mockResolvedValue({ snapshot: "corpus-1", analytics_run_id: "run-1", metrics: { skill_prevalence: page, role_comparison: page, location_distribution: page, skill_cooccurrence: page }, jobs: { data: [{ job_id: "job-1", snapshot_id: "snapshot-1", title: "Backend Engineer", company: "Example", location: null, observed_at: "2026-09-20T00:00:00Z" }], page: { has_more: true, next_cursor: "job-next" } } });
    render(await Dashboard({ searchParams: Promise.resolve({ left_role: "backend_engineer", right_role: "data_engineer" }) }));
    for (const heading of ["Top skills", "Role comparison", "Locations", "Skill co-occurrence", "Jobs"]) expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByLabelText("Corpus snapshot")).toHaveValue("corpus-1");
    expect(screen.getAllByText(/unknown/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("meter")).toHaveLength(5);
    expect(screen.getByText(/backend engineer: 1 of 1 jobs/i)).toBeInTheDocument();
    expect(screen.getByText(/data engineer: 0 of 1 jobs/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View evidence" })).toHaveLength(4);
    expect(screen.getByRole("link", { name: "Backend Engineer" })).toHaveAttribute("href", "/evidence/snapshot-1?snapshot=corpus-1");
    expect(screen.getByRole("link", { name: "Next role comparison page" })).toHaveAttribute("href", expect.stringContaining("left_role=backend_engineer"));
    expect(screen.getByRole("link", { name: "Next role comparison page" })).toHaveAttribute("href", expect.stringContaining("analytics_run_id=run-1"));
    expect(screen.getByRole("link", { name: "Next top skills page" })).toHaveAttribute("href", expect.stringContaining("analytics_run_id=run-1"));
    expect(screen.getByRole("link", { name: "Next top skills page" })).toHaveAttribute("href", expect.stringContaining("left_role=backend_engineer&right_role=data_engineer"));
    expect(screen.getByRole("link", { name: "Next jobs page" })).toHaveAttribute("href", expect.stringContaining("jobs_cursor=job-next"));
    expect(screen.getByRole("link", { name: "Next jobs page" })).toHaveAttribute("href", expect.stringContaining("analytics_run_id=run-1"));
    expect(screen.getByRole("link", { name: "Next jobs page" })).toHaveAttribute("href", expect.stringContaining("left_role=backend_engineer&right_role=data_engineer"));
  });

  it("shows role selection state instead of an empty cohort", async () => {
    const empty = { analytics_run_id: "run-1", data: [], page: { has_more: false, next_cursor: null } };
    mockedLoad.mockResolvedValue({ snapshot: "corpus-1", analytics_run_id: "run-1", metrics: { skill_prevalence: empty, role_comparison: empty, location_distribution: empty, skill_cooccurrence: empty }, jobs: { data: [], page: { has_more: false, next_cursor: null } }, roleComparisonInvalid: true });
    render(await Dashboard({ searchParams: params }));
    expect(screen.getByText("Select two distinct roles to compare cohorts.")).toBeInTheDocument();
  });

  it("does not retain an analytics run in normal role-filter submission", async () => {
    const empty = { analytics_run_id: "run-1", data: [], page: { has_more: false, next_cursor: null } };
    mockedLoad.mockResolvedValue({
      snapshot: "corpus-1",
      analytics_run_id: "run-1",
      metrics: {
        skill_prevalence: empty,
        role_comparison: empty,
        location_distribution: empty,
        skill_cooccurrence: empty,
      },
      jobs: { data: [], page: { has_more: false, next_cursor: null } },
    });
    render(
      await Dashboard({
        searchParams: Promise.resolve({
          analytics_run_id: "run-1",
          left_role: "backend_engineer",
          right_role: "data_engineer",
        }),
      }),
    );
    const form = screen.getByRole("button", { name: "Apply" }).closest("form");
    expect(form).not.toBeNull();
    expect(form?.querySelector('input[name="analytics_run_id"]')).toBeNull();
    expect(form?.querySelector('input[name="left_role"]')).toHaveValue("backend_engineer");
    expect(form?.querySelector('input[name="right_role"]')).toHaveValue("data_engineer");
  });

  it("localizes unpublished role pair errors to the role panel", async () => {
    const statistic = { id: "stat-1", value: "0.5", numerator: 1, denominator: 2, unit: "ratio", dimensions: { skill: "python" }, cutoff: "2026-09-20T00:00:00Z", snapshot: "corpus-1", versions: { metric: "v1", taxonomy: "t1", normalization: "n1", extraction: "e1" }, warning: null, evidence: ["snapshot-1"], metadata: {} };
    const skillPage = { analytics_run_id: "run-1", data: [statistic], page: { has_more: false, next_cursor: null } };
    const empty = { analytics_run_id: "run-1", data: [], page: { has_more: false, next_cursor: null } };
    mockedLoad.mockResolvedValue({
      snapshot: "corpus-1",
      analytics_run_id: "run-1",
      metrics: { skill_prevalence: skillPage, role_comparison: empty, location_distribution: skillPage, skill_cooccurrence: skillPage },
      jobs: { data: [], page: { has_more: false, next_cursor: null } },
      roleComparisonError: { code: "ROLE_PAIR_NOT_FOUND", message: "Requested role pair was not published" },
    });
    render(await Dashboard({ searchParams: Promise.resolve({ left_role: "backend_engineer", right_role: "data_engineer" }) }));
    expect(screen.getByText("This role comparison is not published for the selected cohort.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Top skills" })).toBeInTheDocument();
    expect(screen.getAllByRole("meter")).toHaveLength(3);
  });
});
