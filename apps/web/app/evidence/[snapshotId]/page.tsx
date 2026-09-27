import Link from "next/link";

export default async function EvidencePage({ params, searchParams }: { params: Promise<{ snapshotId: string }>; searchParams: Promise<{ snapshot?: string }> }) {
  const { snapshotId } = await params;
  const { snapshot } = await searchParams;
  const api = process.env.API_URL;
  if (!api || !snapshot) return <main><h1>Evidence unavailable</h1><p>API_URL and corpus snapshot are required.</p><Link href="/">Back to dashboard</Link></main>;
  const query = new URLSearchParams({ snapshot });
  const response = await fetch(`${api}/api/v1/evidence/${encodeURIComponent(snapshotId)}?${query}`, { cache: "no-store" });
  if (!response.ok) return <main><h1>Evidence unavailable</h1><p>Job snapshot could not be loaded.</p><Link href="/">Back to dashboard</Link></main>;
  const evidence = await response.json() as { job: { title: string; company: string; location: string | null; observed_at: string }; description: string; source_url: string | null; raw_record_hash: string };
  return <main><Link href="/">Back to dashboard</Link><article><p className="eyebrow">Job snapshot evidence</p><h1>{evidence.job.title}</h1><p>{evidence.job.company} · {evidence.job.location ?? "Unknown location"}</p><dl><div><dt>Observed</dt><dd>{new Date(evidence.job.observed_at).toLocaleString("en-GB")}</dd></div><div><dt>Raw hash</dt><dd className="hash">{evidence.raw_record_hash}</dd></div></dl><h2>Description</h2><p className="description">{evidence.description}</p>{evidence.source_url && <a href={evidence.source_url} rel="noreferrer">Open original source</a>}</article></main>;
}
