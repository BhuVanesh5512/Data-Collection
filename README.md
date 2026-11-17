# Global Financial-Authority Interest Rates

This repository collects **published interest-rate observations from official monetary and financial authorities**. It is not a stock-market or shares dataset.

## Scope

- **Adaptive historical window:** starts with five years. If fewer than 1,000 genuine official observations are found, the collector expands backwards in five-year steps, up to 30 years or the source's available history. If a manual `START_DATE` is supplied, that exact window is respected.
- **International policy rates:** BIS Central Bank Policy Rates (CBPOL), monthly end-of-period observations for the economies covered by BIS.
- **India policy-rate coverage:** India is included in BIS CBPOL with Reserve Bank of India as its monetary authority. RBI Table 40 is also attempted for Bank Rate, Policy Repo Rate, Fixed Reverse Repo Rate, Standing Deposit Facility (SDF) Rate and Marginal Standing Facility (MSF) Rate. If RBI's changing HTML table cannot be parsed in a run, the collector logs that limitation and retains the verified BIS observations rather than failing the whole collection or inventing RBI rows.
- Only source-published observations are included. No linear interpolation, extrapolation, synthetic rows, share prices, equity returns, or stock-market indicators are collected.

## Official sources

- BIS CBPOL overview: https://data.bis.org/topics/CBPOL
- BIS CBPOL documentation: https://www.bis.org/pages/statistics/cbpol-doc.pdf
- RBI Table 40, Major Monetary Policy Rates and Reserve Requirements: https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=23865
- RBI DBIE portal: https://data.rbi.org.in/

BIS says its policy-rate series are selected in collaboration with the participating central banks, cover more than 40 advanced and emerging market economies, and are disseminated daily and monthly. Monthly observations are the value on the last business day of the month. RBI's Table 40 publishes effective-date changes in India's key monetary policy rates.

## Authority and bank-name fields

- `authority_name` is the official financial/monetary authority publishing or supplying the rate.
- `bank_name` is retained for compatibility with the earlier project schema and is set equal to `authority_name`. It is not a commercial-bank name unless a source explicitly identifies a commercial bank.
- For India, the authority is **Reserve Bank of India**.
- For BIS reference areas, the authority name is mapped to the corresponding central bank or monetary authority, including the Croatian National Bank for Croatia. Unknown BIS reference-area codes cause collection to fail instead of receiving a guessed name.
- `bank_name_status` indicates that the authority name is identified.

## Output

Primary file: `data/processed/global_bank_interest_rates.csv`

Important columns include:
- Geography: `country`, `country_code`, `iso3`, `entity_type`
- Authority: `authority_name`, `bank_name`, `bank_name_status`, `institution_name`, `institution_type`
- Rate: `rate_type`, `rate_name`, `interest_rate`, `units`
- Time: `observation_date`, `year`, `month`, `reference_period`, `frequency`
- Provenance: `source_name`, `source_url`, `series_code`, `rate_definition`, `source_retrieved_at`
- Quality: `is_estimated`, `observation_status`, `collection_window_start`, `methodology_notes`

BIS observations use `frequency=monthly` and month-end reference periods. RBI observations use `frequency=event` and the source's effective date. These frequencies must remain distinct in analysis. The rate instrument is identified by `rate_name` and `series_code`; do not combine different instruments as though they were one rate.

## Verification

Each workflow run independently downloads the BIS source and attempts to re-read RBI Table 40. It compares every collected dataset value against the matching official source. The verification summary explicitly reports how many RBI observations were available; when RBI's HTML table cannot be parsed, only BIS observations are verified and the limitation is recorded. It writes:
- `data/processed/source_verification.csv`
- `data/processed/source_verification_summary.json`
- `data/processed/analysis_ready_rates.csv`: analysis features added without changing the original observations (consecutive month changes, previous observation change, 12-month rolling mean/standard deviation, latest-observation flags, and review flags for large changes/high values).
- `data/processed/country_series_summary.csv`: per-country/region series statistics, latest observation, first-to-latest change, missing months, and coverage status.
- `data/processed/monthly_cross_section_summary.csv`: month-by-month median, mean, quartiles, min/max and balanced-panel median.
- `data/processed/data_quality_report.json`: verification status, coverage exceptions, latest observations, negative values and high-rate review records.
- `data/processed/analysis_insights.md`: automatically generated findings and interpretation cautions.

The workflow fails if any observation cannot be matched, a value differs, an authority name is missing, an estimated row is present, or duplicate logical observations are found. Verification checks exact source values; it does not claim that all countries publish comparable policy instruments.

## Coverage limitations

BIS CBPOL currently covers more than 40 economies, not every country. RBI adds several official Indian policy-rate instruments. The total number of rows and countries therefore depends on actual source coverage and available observations. The collector starts with five years and expands backwards in five-year steps only if genuine source observations remain below 1,000, up to 30 years. It reports the actual count if official source coverage is still below the target. It never generates or interpolates data to meet a row target.

## Automation

GitHub Actions can be run manually from **Actions → Collect and verify global financial-authority interest rates → Run workflow**. It is also scheduled monthly. The workflow collects, independently verifies, and commits only the official-observation CSV and audit reports.

## Attribution

Retain the source URLs and metadata in every analysis. Follow BIS permitted-use guidance: https://data.bis.org/help/legal. RBI data should be attributed to the Reserve Bank of India. This repository is not affiliated with or endorsed by either authority.


## Column guide and analysis use

### Core columns in the official observation file
- `observation_id`: row identifier for this exported file; not a source-issued ID.
- `country`, `source_country_name`, `country_code`, `iso3`, `entity_type`: geography and whether the observation is a country or a regional reference area. Euro area is a regional aggregate and has no ISO3 country code.
- `bank_name`, `authority_name`, `monetary_authority_name`: mapped monetary authority. In this policy-rate extract these fields identify the central bank/authority, not a commercial bank.
- `bank_name_status`, `institution_type`, `institution_name_note`: authority-identification status and institution classification/context.
- `observation_date`, `year`, `month`, `reference_period`: date keys. For BIS monthly data, `reference_period` is YYYY-MM and `observation_date` is represented as the first day of that month; it is not a daily effective date.
- `interest_rate`, `units`: published rate value and unit (percent per year).
- `rate_type`, `rate_name`, `series_code`, `series_name`, `rate_definition`: rate family, instrument label, source-series identifier and definition. Use these fields to avoid comparing unlike policy instruments.
- `frequency`, `original_frequency`: frequency in this extract and source frequency. BIS observations are monthly.
- `source_name`, `source_url`, `monetary_authority_source_url`, `source_retrieved_at`: provenance and collection timestamp.
- `is_estimated`, `observation_status`, `estimation_method`, `methodology_notes`: whether the observation is source-published and explanatory processing notes. Official-only rows should have `is_estimated=False`.
- `collection_window_start`: start date used by the collector for this export.

### Best fields for common analyses
- Trend line: `reference_period` on the x-axis, `interest_rate` on the y-axis, filtered to one `series_code` or `rate_name`.
- Country comparison: compare the latest available observation per series, but display its `reference_period` and coverage status.
- Authority comparison: `authority_name` with `interest_rate`; use one comparable rate instrument.
- Change analysis: use `analysis_ready_rates.csv` and `change_from_previous_month_pp`. This field is blank when observations are not consecutive months.
- Volatility: use `rolling_12m_std` or country summary `standard_deviation_pp`; interpret only with enough consecutive observations.
- Coverage: use `country_series_summary.csv` fields `coverage_pct`, `missing_months_in_window`, `months_behind_latest_dataset_period`, and `coverage_status`.

### Interpretation cautions
- Cross-sectional mean/median are descriptive summaries of the available authority series, not an economically weighted global interest rate.
- The balanced-panel median compares the same complete series over time and reduces changes caused solely by entities entering/leaving the dataset.
- Very high rates are retained if they match the source. They are flagged for context rather than automatically treated as errors.
- Negative rates are valid observations when published by the authority.
- A policy rate is not the same as commercial lending, deposit, mortgage or credit-card rates.
