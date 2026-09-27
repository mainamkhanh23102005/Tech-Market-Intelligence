export type Statistic = {
  id: string;
  value: string;
  numerator: number;
  denominator: number;
  unit: string;
  dimensions: Record<string, string>;
  cutoff: string;
  snapshot: string;
  versions: { metric: string; taxonomy: string; normalization: string; extraction: string };
  warning: string | null;
  evidence: string[];
  metadata: Record<string, number>;
};

export type Job = {
  job_id: string;
  snapshot_id: string;
  title: string;
  company: string;
  location: string | null;
  observed_at: string;
};

export type MarketPage = {
  analytics_run_id: string;
  data: Statistic[];
  page: { next_cursor: string | null; has_more: boolean };
};

export type JobsPage = {
  data: Job[];
  page: { next_cursor: string | null; has_more: boolean };
};

export class MarketApiError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "MarketApiError";
    this.code = code;
  }
}

export type DashboardData = {
  snapshot: string;
  analytics_run_id: string;
  metrics: Record<string, MarketPage>;
  jobs: JobsPage;
  roleComparisonInvalid?: boolean;
  roleComparisonError?: { code: string; message: string };
};

const metricNames = [
  "skill_prevalence",
  "role_comparison",
  "location_distribution",
  "skill_cooccurrence",
] as const;

const rolePanelCodes = new Set(["ROLE_PAIR_NOT_FOUND", "ROLE_PAIR_INVALID"]);

async function loadMarketPage(url: string, expectedRun?: string): Promise<MarketPage> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    let code = "MARKET_ERROR";
    let message = "Market data unavailable";
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) {
        code = body.error.code;
        message = body.error.message ?? message;
      }
    } catch {
      // keep defaults for non-JSON error bodies
    }
    throw new MarketApiError(code, message);
  }
  const page = (await response.json()) as Partial<MarketPage>;
  if (!page.analytics_run_id) {
    throw new MarketApiError("MISSING_RUN_ID", "Resolved analytics_run_id is required");
  }
  if (expectedRun && page.analytics_run_id !== expectedRun) {
    throw new MarketApiError("RUN_MISMATCH", "Market response used a different analytics run");
  }
  return page as MarketPage;
}

async function loadJobsPage(url: string): Promise<JobsPage> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new MarketApiError("JOBS_ERROR", "Market data unavailable");
  return (await response.json()) as JobsPage;
}

function marketUrl(
  api: string,
  metric: string,
  query: URLSearchParams,
): string {
  return `${api}/api/v1/market/${metric}?${query}`;
}

export async function loadDashboard(
  search: Record<string, string | undefined>,
): Promise<DashboardData | null> {
  const api = process.env.API_URL;
  const snapshot = search.snapshot ?? process.env.CORPUS_SNAPSHOT_ID;
  if (!api || !snapshot) return null;
  const limit = "10";
  const leftRole = search.left_role ?? process.env.ROLE_COMPARISON_LEFT_ROLE;
  const rightRole = search.right_role ?? process.env.ROLE_COMPARISON_RIGHT_ROLE;
  const roleComparisonInvalid = !leftRole || !rightRole || leftRole === rightRole;
  const pinnedRun =
    search.analytics_run_id ??
    search.skill_prevalence_run ??
    search.role_comparison_run ??
    search.location_distribution_run ??
    search.skill_cooccurrence_run;

  let resolvedRun = pinnedRun;
  let skillPage: MarketPage | undefined;
  let rolePage: MarketPage | undefined;
  let roleComparisonError: DashboardData["roleComparisonError"];

  if (!resolvedRun && !roleComparisonInvalid) {
    const roleQuery = new URLSearchParams({
      snapshot,
      limit,
      left_role: leftRole,
      right_role: rightRole,
    });
    const roleCursor = search.role_comparison_cursor;
    if (roleCursor) roleQuery.set("cursor", roleCursor);
    try {
      rolePage = await loadMarketPage(marketUrl(api, "role_comparison", roleQuery));
      resolvedRun = rolePage.analytics_run_id;
    } catch (error) {
      if (error instanceof MarketApiError && rolePanelCodes.has(error.code)) {
        roleComparisonError = { code: error.code, message: error.message };
      } else {
        throw error;
      }
    }
  }

  if (!resolvedRun) {
    const skillQuery = new URLSearchParams({ snapshot, limit });
    const skillCursor = search.skill_prevalence_cursor;
    if (skillCursor) skillQuery.set("cursor", skillCursor);
    skillPage = await loadMarketPage(marketUrl(api, "skill_prevalence", skillQuery));
    resolvedRun = skillPage.analytics_run_id;
  }
  const analyticsRunId = resolvedRun;

  if (roleComparisonError) {
    rolePage = {
      analytics_run_id: analyticsRunId,
      data: [],
      page: { next_cursor: null, has_more: false },
    };
  }

  const metricsEntries = await Promise.all(
    metricNames.map(async (metric): Promise<[string, MarketPage]> => {
      if (metric === "skill_prevalence" && skillPage) {
        return [metric, skillPage];
      }
      if (metric === "role_comparison" && rolePage) {
        return [metric, rolePage];
      }
      const query = new URLSearchParams({ snapshot, limit, analytics_run_id: analyticsRunId });
      const cursor = search[`${metric}_cursor`];
      if (cursor) query.set("cursor", cursor);
      if (metric === "role_comparison") {
        if (roleComparisonInvalid) {
          return [
            metric,
            { analytics_run_id: analyticsRunId, data: [], page: { next_cursor: null, has_more: false } },
          ];
        }
        query.set("left_role", leftRole as string);
        query.set("right_role", rightRole as string);
        try {
          return [metric, await loadMarketPage(marketUrl(api, metric, query), analyticsRunId)];
        } catch (error) {
          if (error instanceof MarketApiError && rolePanelCodes.has(error.code)) {
            roleComparisonError = { code: error.code, message: error.message };
            return [
              metric,
              { analytics_run_id: analyticsRunId, data: [], page: { next_cursor: null, has_more: false } },
            ];
          }
          throw error;
        }
      }
      return [metric, await loadMarketPage(marketUrl(api, metric, query), analyticsRunId)];
    }),
  );
  if (metricsEntries.some(([, page]) => page.analytics_run_id !== analyticsRunId)) {
    throw new MarketApiError("RUN_MISMATCH", "Market response did not match selected analytics run");
  }

  const jobQuery = new URLSearchParams({ snapshot, limit });
  if (search.jobs_cursor) jobQuery.set("cursor", search.jobs_cursor);
  const jobs = await loadJobsPage(`${api}/api/v1/jobs?${jobQuery}`);

  return {
    snapshot,
    analytics_run_id: analyticsRunId,
    metrics: Object.fromEntries(metricsEntries),
    jobs,
    roleComparisonInvalid,
    roleComparisonError,
  };
}
