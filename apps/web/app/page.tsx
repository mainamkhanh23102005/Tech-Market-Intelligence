import Link from "next/link";

import { DashboardData, loadDashboard, MarketPage, Statistic } from "../lib/market";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function percent(numerator: number, denominator: number): string {
  return denominator > 0 ? ((numerator / denominator) * 100).toFixed(1) : "0.0";
}

function StatisticValue({
  title,
  metric,
  item,
}: {
  title: string;
  metric: string;
  item: Statistic;
}) {
  if (metric === "role_comparison") {
    const leftNumerator = item.metadata.left_numerator;
    const rightNumerator = item.metadata.right_numerator;
    const leftDenominator = item.metadata.left_denominator;
    const rightDenominator = item.metadata.right_denominator;
    const skill = label(item.dimensions.skill ?? "skill");
    const leftRole = label(item.dimensions.left_role ?? "left role");
    const rightRole = label(item.dimensions.right_role ?? "right role");

    if (
      [leftNumerator, rightNumerator, leftDenominator, rightDenominator].every(
        (value) => typeof value === "number",
      )
    ) {
      return (
        <>
          <strong>{skill}</strong>
          <div className="comparison">
            <div>
              <p>
                {leftRole}: {leftNumerator} of {leftDenominator} jobs ·{" "}
                {percent(leftNumerator, leftDenominator)}%
              </p>
              <meter
                min="0"
                max="1"
                value={leftDenominator > 0 ? leftNumerator / leftDenominator : 0}
                aria-label={`${skill} prevalence for ${leftRole}`}
              />
            </div>
            <div>
              <p>
                {rightRole}: {rightNumerator} of {rightDenominator} jobs ·{" "}
                {percent(rightNumerator, rightDenominator)}%
              </p>
              <meter
                min="0"
                max="1"
                value={rightDenominator > 0 ? rightNumerator / rightDenominator : 0}
                aria-label={`${skill} prevalence for ${rightRole}`}
              />
            </div>
          </div>
        </>
      );
    }
  }

  const dimensions = Object.values(item.dimensions).map(label).join(" · ");
  return (
    <>
      <strong>{dimensions}</strong>
      <p>
        {item.numerator} of {item.denominator} jobs · {(Number(item.value) * 100).toFixed(1)}%
      </p>
      <meter
        min="0"
        max="1"
        value={Number(item.value)}
        aria-label={`${title} ${dimensions}`}
      />
    </>
  );
}

function MetricSection({
  title,
  metric,
  page,
  snapshot,
  roleComparisonInvalid = false,
  roleComparisonError,
  roleQuery,
}: {
  title: string;
  metric: string;
  page: MarketPage;
  snapshot: string;
  roleComparisonInvalid?: boolean;
  roleComparisonError?: { code: string; message: string };
  roleQuery: string;
}) {
  const roleMessage =
    roleComparisonError?.code === "ROLE_PAIR_NOT_FOUND"
      ? "This role comparison is not published for the selected cohort."
      : roleComparisonError?.code === "ROLE_PAIR_INVALID"
        ? "Select two distinct roles to compare cohorts."
        : roleComparisonError
          ? roleComparisonError.message
          : null;
  return (
    <section aria-labelledby={`${metric}-heading`}>
      <h2 id={`${metric}-heading`}>{title}</h2>
      {roleComparisonInvalid ? (
        <p role="status">Select two distinct roles to compare cohorts.</p>
      ) : roleMessage ? (
        <p role="status">{roleMessage}</p>
      ) : page.data.length === 0 ? (
        <p role="status">No results for this cohort.</p>
      ) : (
        <ol className="skills">
          {page.data.map((item) => (
            <li key={item.id}>
              <StatisticValue title={title} metric={metric} item={item} />
              <dl>
                <div>
                  <dt>Cutoff</dt>
                  <dd>{new Date(item.cutoff).toLocaleDateString("en-GB")}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{item.versions.metric}</dd>
                </div>
              </dl>
              {item.warning && (
                <p role="note" className="warning">
                  {item.warning}
                </p>
              )}
              <nav aria-label={`Evidence for ${Object.values(item.dimensions).join(" ")}`}>
                {item.evidence.map((id) => (
                  <Link key={id} href={`/evidence/${id}?snapshot=${snapshot}`}>
                    View evidence
                  </Link>
                ))}
              </nav>
            </li>
          ))}
        </ol>
      )}
      {page.page.has_more && page.page.next_cursor && (
        <Link
          className="next"
          href={`/?snapshot=${snapshot}&${metric}_cursor=${page.page.next_cursor}&analytics_run_id=${encodeURIComponent(page.analytics_run_id)}${roleQuery}#${metric}-heading`}
        >
          Next {title.toLowerCase()} page
        </Link>
      )}
    </section>
  );
}

export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const result = await safeLoad(params);
  if (result.error) return <ErrorState />;
  const data = result.data;
  if (!data) {
    return (
      <main>
        <Header />
        <section role="status" className="empty">
          <h2>No published snapshot</h2>
          <p>Configure API_URL and CORPUS_SNAPSHOT_ID after analytics publication.</p>
        </section>
      </main>
    );
  }
  const leftRole = params.left_role ?? process.env.ROLE_COMPARISON_LEFT_ROLE;
  const rightRole = params.right_role ?? process.env.ROLE_COMPARISON_RIGHT_ROLE;
  const roleQuery =
    leftRole && rightRole
      ? `&left_role=${encodeURIComponent(leftRole)}&right_role=${encodeURIComponent(rightRole)}`
      : "";
  return (
    <main>
      <Header />
      <form action="/" className="filters">
        <label htmlFor="snapshot">Corpus snapshot</label>
        <input id="snapshot" name="snapshot" defaultValue={data.snapshot} required />
        <label htmlFor="left-role">Left role</label>
        <input id="left-role" name="left_role" defaultValue={params.left_role ?? process.env.ROLE_COMPARISON_LEFT_ROLE ?? ""} />
        <label htmlFor="right-role">Right role</label>
        <input id="right-role" name="right_role" defaultValue={params.right_role ?? process.env.ROLE_COMPARISON_RIGHT_ROLE ?? ""} />
        <button type="submit">Apply</button>
      </form>
      <MetricSection
        title="Top skills"
        metric="skill_prevalence"
        page={data.metrics.skill_prevalence}
        snapshot={data.snapshot}
        roleQuery={roleQuery}
      />
      <MetricSection
        title="Role comparison"
        metric="role_comparison"
        page={data.metrics.role_comparison}
        snapshot={data.snapshot}
        roleComparisonInvalid={data.roleComparisonInvalid}
        roleComparisonError={data.roleComparisonError}
        roleQuery={roleQuery}
      />
      <MetricSection
        title="Locations"
        metric="location_distribution"
        page={data.metrics.location_distribution}
        snapshot={data.snapshot}
        roleQuery={roleQuery}
      />
      <MetricSection
        title="Skill co-occurrence"
        metric="skill_cooccurrence"
        page={data.metrics.skill_cooccurrence}
        snapshot={data.snapshot}
        roleQuery={roleQuery}
      />
      <section aria-labelledby="jobs-heading">
        <h2 id="jobs-heading">Jobs</h2>
        <ul className="jobs">
          {data.jobs.data.map((job) => (
            <li key={job.snapshot_id}>
              <Link href={`/evidence/${job.snapshot_id}?snapshot=${data.snapshot}`}>{job.title}</Link>
              <span>
                {job.company} · {job.location ?? "Unknown location"}
              </span>
            </li>
          ))}
        </ul>
        {data.jobs.page.has_more && data.jobs.page.next_cursor && (
          <Link
            className="next"
            href={`/?snapshot=${data.snapshot}&jobs_cursor=${data.jobs.page.next_cursor}&analytics_run_id=${encodeURIComponent(data.analytics_run_id)}${roleQuery}#jobs-heading`}
          >
            Next jobs page
          </Link>
        )}
      </section>
    </main>
  );
}

async function safeLoad(
  search: Record<string, string | undefined>,
): Promise<{ data: DashboardData | null; error: boolean }> {
  try {
    return { data: await loadDashboard(search), error: false };
  } catch {
    return { data: null, error: true };
  }
}

export function ErrorState() {
  return (
    <main>
      <Header />
      <section role="alert" className="empty">
        <h2>Market data unavailable</h2>
        <p>API request failed. Try again after service recovers.</p>
      </section>
    </main>
  );
}

function Header() {
  return (
    <header>
      <p className="eyebrow">Observed technical jobs</p>
      <h1>Market evidence</h1>
      <p>
        Deterministic statistics from one immutable corpus snapshot. Results describe collected
        sources, not whole labor market.
      </p>
    </header>
  );
}
