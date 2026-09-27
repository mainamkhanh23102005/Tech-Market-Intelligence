import { afterEach, describe, expect, it, vi } from "vitest";
import { loadDashboard, MarketApiError } from "./market";

const response = (analytics_run_id: string) => ({
  ok: true,
  json: async () => ({ analytics_run_id, data: [], page: { has_more: false, next_cursor: null } }),
});

const jobsResponse = () => ({
  ok: true,
  json: async () => ({ data: [], page: { has_more: false, next_cursor: null } }),
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("loadDashboard", () => {
  it("pins one resolved analytics_run_id across all metrics and pagination", async () => {
    const fetch = vi.fn(async (url: string) => {
      if (new URL(url).pathname.endsWith("/jobs")) return jobsResponse();
      return response(new URL(url).searchParams.get("analytics_run_id") ?? "run-a");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    await loadDashboard({
      snapshot: "corpus-a",
      skill_prevalence_cursor: "cursor-a",
      analytics_run_id: "run-a",
      left_role: "platform_engineer",
      right_role: "data_engineer",
      role_comparison_cursor: "cursor-role",
      role_comparison_run: "run-a",
      location_distribution_run: "run-a",
      skill_cooccurrence_run: "run-a",
    });
    const urls = fetch.mock.calls
      .map(([url]) => new URL(url as string))
      .filter((url) => url.pathname.includes("/market/"));
    expect(urls.length).toBe(4);
    for (const url of urls) {
      expect(url.searchParams.get("analytics_run_id")).toBe("run-a");
    }
    const skills = urls.find((url) => url.pathname.endsWith("skill_prevalence"));
    const comparison = urls.find((url) => url.pathname.endsWith("role_comparison"));
    expect(skills?.searchParams.get("cursor")).toBe("cursor-a");
    expect(skills?.searchParams.get("snapshot")).toBe("corpus-a");
    expect(comparison?.searchParams.get("cursor")).toBe("cursor-role");
    expect(comparison?.searchParams.get("left_role")).toBe("platform_engineer");
    expect(comparison?.searchParams.get("right_role")).toBe("data_engineer");
  });

  it("resolves an unpinned ordered role pair before newer generic publications and pins every panel", async () => {
    let latestGenericRun = "run-newer-cd";
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (
        parsed.pathname.endsWith("role_comparison") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        expect(parsed.searchParams.get("left_role")).toBe("backend_engineer");
        expect(parsed.searchParams.get("right_role")).toBe("data_engineer");
        latestGenericRun = "run-published-during-load";
        return response("run-compatible-ab");
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? latestGenericRun);
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({
      snapshot: "corpus-a",
      left_role: "backend_engineer",
      right_role: "data_engineer",
    });
    expect(data?.analytics_run_id).toBe("run-compatible-ab");
    const marketUrls = fetch.mock.calls
      .map(([url]) => new URL(url as string))
      .filter((url) => url.pathname.includes("/market/"));
    expect(marketUrls).toHaveLength(4);
    expect(marketUrls[0].pathname).toMatch(/role_comparison$/);
    expect(marketUrls[0].searchParams.has("analytics_run_id")).toBe(false);
    expect(
      marketUrls.filter((url) => url.pathname.endsWith("role_comparison")),
    ).toHaveLength(1);
    for (const url of marketUrls.slice(1)) {
      expect(url.searchParams.get("analytics_run_id")).toBe("run-compatible-ab");
    }
    expect(data?.metrics.skill_prevalence.analytics_run_id).toBe("run-compatible-ab");
    expect(data?.metrics.role_comparison.analytics_run_id).toBe("run-compatible-ab");
    expect(data?.metrics.location_distribution.analytics_run_id).toBe("run-compatible-ab");
    expect(data?.metrics.skill_cooccurrence.analytics_run_id).toBe("run-compatible-ab");
  });

  it("falls back to one generic publication when an unpinned role pair is unavailable", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (
        parsed.pathname.endsWith("role_comparison") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        return {
          ok: false,
          json: async () => ({
            error: { code: "ROLE_PAIR_NOT_FOUND", message: "Requested role pair was not published" },
          }),
        };
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? "run-generic");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({
      snapshot: "corpus-a",
      left_role: "backend_engineer",
      right_role: "data_engineer",
    });
    expect(data?.analytics_run_id).toBe("run-generic");
    expect(data?.roleComparisonError?.code).toBe("ROLE_PAIR_NOT_FOUND");
    expect(data?.metrics.role_comparison).toEqual({
      analytics_run_id: "run-generic",
      data: [],
      page: { has_more: false, next_cursor: null },
    });
    const marketUrls = fetch.mock.calls
      .map(([url]) => new URL(url as string))
      .filter((url) => url.pathname.includes("/market/"));
    expect(marketUrls[0].pathname).toMatch(/role_comparison$/);
    const genericResolver = marketUrls[1];
    expect(genericResolver.pathname).toMatch(/skill_prevalence$/);
    expect(genericResolver.searchParams.has("analytics_run_id")).toBe(false);
    for (const url of marketUrls.slice(2)) {
      expect(url.searchParams.get("analytics_run_id")).toBe("run-generic");
    }
  });

  it("keeps generic fallback failures global after a missing unpinned role pair", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (
        parsed.pathname.endsWith("role_comparison") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        return {
          ok: false,
          json: async () => ({
            error: { code: "ROLE_PAIR_NOT_FOUND", message: "Requested role pair was not published" },
          }),
        };
      }
      if (
        parsed.pathname.endsWith("skill_prevalence") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        return {
          ok: false,
          json: async () => ({ error: { code: "PUBLICATION_NOT_FOUND", message: "missing" } }),
        };
      }
      throw new Error("no additional market resolver should run");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    await expect(
      loadDashboard({
        snapshot: "corpus-a",
        left_role: "backend_engineer",
        right_role: "data_engineer",
      }),
    ).rejects.toMatchObject({
      name: "MarketApiError",
      code: "PUBLICATION_NOT_FOUND",
    });
    const marketUrls = fetch.mock.calls
      .map(([url]) => new URL(url as string))
      .filter((url) => url.pathname.includes("/market/"));
    expect(marketUrls).toHaveLength(2);
    expect(marketUrls[0].pathname).toMatch(/role_comparison$/);
    expect(marketUrls[1].pathname).toMatch(/skill_prevalence$/);
  });

  it("keeps an explicitly pinned incompatible run and localizes its role error", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("role_comparison")) {
        return {
          ok: false,
          json: async () => ({
            error: { code: "ROLE_PAIR_NOT_FOUND", message: "Requested role pair was not published" },
          }),
        };
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? "unexpected-unpinned-run");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({
      snapshot: "corpus-a",
      analytics_run_id: "run-pinned-cd",
      left_role: "backend_engineer",
      right_role: "data_engineer",
    });
    expect(data?.analytics_run_id).toBe("run-pinned-cd");
    expect(data?.roleComparisonError?.code).toBe("ROLE_PAIR_NOT_FOUND");
    const marketUrls = fetch.mock.calls
      .map(([url]) => new URL(url as string))
      .filter((url) => url.pathname.includes("/market/"));
    expect(marketUrls).toHaveLength(4);
    for (const url of marketUrls) {
      expect(url.searchParams.get("analytics_run_id")).toBe("run-pinned-cd");
    }
  });

  it("localizes ROLE_PAIR_INVALID for an explicitly pinned run", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("role_comparison")) {
        return {
          ok: false,
          json: async () => ({
            error: { code: "ROLE_PAIR_INVALID", message: "Role comparison requires two roles" },
          }),
        };
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? "unexpected-unpinned-run");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({
      snapshot: "corpus-a",
      analytics_run_id: "run-pinned",
      left_role: "backend_engineer",
      right_role: "data_engineer",
    });
    expect(data?.roleComparisonError?.code).toBe("ROLE_PAIR_INVALID");
    expect(data?.metrics.role_comparison.analytics_run_id).toBe("run-pinned");
  });

  it("keeps role transport and unrecognized server failures global", async () => {
    for (const failure of [
      () => Promise.reject(new Error("network unavailable")),
      () =>
        Promise.resolve({
          ok: false,
          json: async () => ({ error: { code: "MARKET_ERROR", message: "server unavailable" } }),
        }),
    ]) {
      const fetch = vi.fn(async (url: string) => {
        const parsed = new URL(url);
        if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
        if (parsed.pathname.endsWith("role_comparison")) return failure();
        return response(parsed.searchParams.get("analytics_run_id") ?? "run-generic");
      });
      vi.stubGlobal("fetch", fetch);
      vi.stubEnv("API_URL", "https://api.example.test");
      await expect(
        loadDashboard({
          snapshot: "corpus-a",
          left_role: "backend_engineer",
          right_role: "data_engineer",
        }),
      ).rejects.toBeInstanceOf(Error);
      vi.unstubAllGlobals();
      vi.unstubAllEnvs();
    }
  });

  it("rejects a response that violates the pinned analytics run", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("location_distribution")) return response("run-newer");
      return response(parsed.searchParams.get("analytics_run_id") ?? "run-original");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    await expect(loadDashboard({ snapshot: "corpus-a" })).rejects.toMatchObject({
      name: "MarketApiError",
      code: "RUN_MISMATCH",
    });
  });

  it("localizes role pair failures to the role panel without failing the dashboard", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("role_comparison")) {
        return {
          ok: false,
          json: async () => ({
            error: { code: "ROLE_PAIR_NOT_FOUND", message: "Requested role pair was not published" },
          }),
        };
      }
      if (
        parsed.pathname.endsWith("skill_prevalence") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        return response("run-coherent");
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? "run-coherent");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({
      snapshot: "corpus-a",
      left_role: "backend_engineer",
      right_role: "data_engineer",
    });
    expect(data?.analytics_run_id).toBe("run-coherent");
    expect(data?.roleComparisonError?.code).toBe("ROLE_PAIR_NOT_FOUND");
    expect(data?.metrics.role_comparison.data).toEqual([]);
    expect(data?.metrics.role_comparison.analytics_run_id).toBe("run-coherent");
    expect(data?.metrics.skill_prevalence.analytics_run_id).toBe("run-coherent");
    expect(data?.metrics.location_distribution.analytics_run_id).toBe("run-coherent");
  });

  it("throws foundational market failures so the dashboard can show a global error", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("skill_prevalence")) {
        return {
          ok: false,
          json: async () => ({ error: { code: "SNAPSHOT_NOT_FOUND", message: "missing" } }),
        };
      }
      return response("run-x");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    await expect(loadDashboard({ snapshot: "corpus-a" })).rejects.toMatchObject({
      name: "MarketApiError",
      code: "SNAPSHOT_NOT_FOUND",
    });
    await expect(loadDashboard({ snapshot: "corpus-a" })).rejects.toBeInstanceOf(MarketApiError);
  });

  it("keeps an invalid role selection local without calling the role endpoint", async () => {
    const fetch = vi.fn(async (url: string) => {
      const parsed = new URL(url);
      if (parsed.pathname.endsWith("/jobs")) return jobsResponse();
      if (parsed.pathname.endsWith("role_comparison")) {
        throw new Error("role endpoint should not be called");
      }
      if (
        parsed.pathname.endsWith("skill_prevalence") &&
        !parsed.searchParams.has("analytics_run_id")
      ) {
        return response("run-1");
      }
      return response(parsed.searchParams.get("analytics_run_id") ?? "run-1");
    });
    vi.stubGlobal("fetch", fetch);
    vi.stubEnv("API_URL", "https://api.example.test");
    const data = await loadDashboard({ snapshot: "corpus-a" });
    expect(data?.roleComparisonInvalid).toBe(true);
    expect(data?.metrics.role_comparison.data).toEqual([]);
    expect(data?.analytics_run_id).toBe("run-1");
  });
});
