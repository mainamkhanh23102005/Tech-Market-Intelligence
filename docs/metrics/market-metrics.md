# Metric Definitions

## Shared semantics

Every statistic carries value, numerator, denominator, unit, dimensions, source cutoff, immutable corpus snapshot ID, metric/taxonomy/normalization/extraction version tuple, coverage warning, and exact evidence snapshot IDs. Cohorts count distinct logical jobs once. Corpus selection chooses latest `observed_at <= cutoff`; greatest snapshot UUID breaks equal-time ties. Unknown role, seniority, location, and work arrangement remain explicit `unknown` dimensions. Skill evidence includes only `job_skills.reviewed_state = 'accepted'` matching run taxonomy and extraction versions. Skills repeat at most once per logical job.

Market read endpoints order statistics by value descending and use statistic UUID as the deterministic tie-break and pagination cursor. First request may select latest successful publication; every response includes its `analytics_run_id`. Later requests send that ID explicitly. A cursor is valid only within same corpus snapshot, analytics run, metric, and selected role pair when applicable. Foreign, missing, unsuccessful, or incompatible run IDs never fall back to latest.

Samples below 10 distinct logical jobs receive `Small sample: N distinct logical jobs; interpret cautiously.` Synthetic fixtures cannot support representative market claims.

## `skill_prevalence` — `skill-prevalence-1.0.0`

Numerator: distinct cohort jobs containing accepted evidence for skill. Denominator: all distinct jobs in cohort. Unit: ratio. Dimensions: skill, role, seniority, location, work arrangement.

## `role_comparison` — `role-comparison-1.0.0`

Reports skill prevalence for two role cohorts with separate left/right numerators and denominators. Combined value exists for contract completeness; the API exposes the per-role counts in statistic metadata and consumers must present both cohort fractions.

## `location_distribution` — `location-distribution-1.0.0`

Numerator: distinct cohort jobs in location or explicit `unknown`. Denominator: all distinct jobs in cohort. Dimensions: location and optionally work arrangement.

## `skill_cooccurrence` — `skill-cooccurrence-1.0.0`

Numerator: distinct cohort jobs with accepted evidence for both canonical skills. Denominator: all distinct jobs in cohort. Skill pair ordering is lexical, preventing duplicate reversed pairs.
