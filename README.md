# Global Financial-Authority Interest Rates

This repository collects **published interest-rate observations from official monetary and financial authorities**. It is not a stock-market or shares dataset.

## Scope

- **Adaptive historical window:** starts with five years. If fewer than 1,000 genuine official observations are found, the collector expands backwards in five-year steps, up to 30 years or the source's available history. If a manual `START_DATE` is supplied, that exact window is respected.
- **International policy rates:** BIS Central Bank Policy Rates (CBPOL), monthly end-of-period observations for the economies covered by BIS.
- **India policy-rate instruments:** Reserve Bank of India (RBI) Table 40 effective-date observations for Bank Rate, Policy Repo Rate, Fixed Reverse Repo Rate, Standing Deposit Facility (SDF) Rate and Marginal Standing Facility (MSF) Rate.
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

Each workflow run independently downloads the current BIS and RBI source tables again and compares every dataset value against the official source. It writes:
- `data/processed/source_verification.csv`
- `data/processed/source_verification_summary.json`

The workflow fails if any observation cannot be matched, a value differs, an authority name is missing, an estimated row is present, or duplicate logical observations are found. Verification checks exact source values; it does not claim that all countries publish comparable policy instruments.

## Coverage limitations

BIS CBPOL currently covers more than 40 economies, not every country. RBI adds several official Indian policy-rate instruments. The total number of rows and countries therefore depends on actual source coverage and available observations. The collector starts with five years and expands backwards in five-year steps only if genuine source observations remain below 1,000, up to 30 years. It reports the actual count if official source coverage is still below the target. It never generates or interpolates data to meet a row target.

## Automation

GitHub Actions can be run manually from **Actions → Collect and verify global financial-authority interest rates → Run workflow**. It is also scheduled monthly. The workflow collects, independently verifies, and commits only the official-observation CSV and audit reports.

## Attribution

Retain the source URLs and metadata in every analysis. Follow BIS permitted-use guidance: https://data.bis.org/help/legal. RBI data should be attributed to the Reserve Bank of India. This repository is not affiliated with or endorsed by either authority.
