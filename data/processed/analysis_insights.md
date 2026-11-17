# Dataset analysis and insights

## Dataset scope
- 2,323 verified, official observations across 39 ISO3-coded countries and 1 regional entity/entities.
- Coverage: 2021-11 to 2026-10 (60 monthly periods).
- Rate family: policy; instruments: BIS selected central bank policy rate.
- Frequency: monthly; source: Bank for International Settlements.
- This extract is a policy-rate dataset. It does not contain commercial-bank loan/deposit rates.
- bank_name is an authority label in this dataset, not a commercial bank name.

## Key insights
- The unbalanced cross-sectional median was 1.50% in 2021-11 and 4.25% in 2026-10; reporting coverage changes over time.
- In the balanced panel of 35 complete series, the median was 1.25% at the start and 4.25% at the end. This compares the same set of series across months.
- 35 of 40 authority series have observations in every month of the dataset window.
- 48 observations are negative. Negative policy rates are retained as published, not treated as missing or errors.
- 23 observations exceed 50%; these are flagged for contextual review, not automatically rejected.

### Highest latest observations (within one month of the dataset end)
- Türkiye — 36.000% (2026-10); Central Bank of the Republic of Türkiye.
- Russian Federation — 14.000% (2026-10); Bank of Russia.
- Brazil — 13.750% (2026-10); Central Bank of Brazil.
- Colombia — 12.250% (2026-10); Bank of the Republic (Banco de la República).
- Iceland — 8.000% (2026-10); Central Bank of Iceland.

### Largest increases among fully covered series
- Türkiye: +21.00 percentage points from 15.000% to 36.000%.
- Colombia: +9.75 percentage points from 2.500% to 12.250%.
- Russian Federation: +6.50 percentage points from 7.500% to 14.000%.
- Iceland: +6.00 percentage points from 2.000% to 8.000%.
- Brazil: +6.00 percentage points from 7.750% to 13.750%.

### Largest decreases among fully covered series
- China: -0.85 percentage points from 3.850% to 3.000%.

### Coverage exceptions
- Croatia: 3 observations, 5.0% coverage, latest 2022-07.
- Argentina: 44 observations, 73.3% coverage, latest 2025-06.
- Morocco: 58 observations, 96.7% coverage, latest 2026-08.
- India: 59 observations, 98.3% coverage, latest 2026-09.
- Saudi Arabia: 59 observations, 98.3% coverage, latest 2026-09.

## Interpretation cautions
- Policy-rate instruments differ across jurisdictions; use rate_name and series_code before comparing.
- The cross-sectional mean can be distorted by high-inflation economies; median and country-level trends are often more robust.
- The latest observation is not necessarily the same month for every entity. Always use latest_period and coverage fields.
- A value can match the source and still be stale or incomplete. Verification and coverage are separate quality dimensions.
- A policy rate is not a commercial lending rate, deposit rate, mortgage rate or bank-specific customer rate.

## Generated analysis files
- analysis_ready_rates.csv: source rows plus month-on-month changes, 12-month rolling statistics and review flags.
- country_series_summary.csv: per-country/region coverage, latest rate, range and first-to-latest change.
- monthly_cross_section_summary.csv: monthly cross-sectional distribution.
- data_quality_report.json: verification, coverage exceptions and records requiring review.
