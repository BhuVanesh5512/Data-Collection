# Global Bank Interest Rates Dataset

Automated collection of official global interest-rate statistics using GitHub Actions.

## Coverage
- Central bank policy rates: BIS Central Bank Policy Rates (WS_CBPOL).
- Lending rates: World Bank indicator FR.INR.LEND.
- Deposit rates: World Bank indicator FR.INR.DPST.
- Target observation window: December 2023 through November 2026.

The sources have different reporting frequencies. BIS policy-rate observations may be daily; World Bank lending and deposit indicators are annual. The pipeline preserves the source frequency and never fabricates monthly values or interpolates missing observations.

## Output
`data/processed/global_bank_interest_rates.csv`

The GitHub Actions workflow can be run manually or on a monthly schedule. It commits updated output when the workflow succeeds.

## Data sources and attribution
- BIS, Central bank policy rates (WS_CBPOL): https://data.bis.org/ and https://stats.bis.org/api/v1/data/WS_CBPOL/.?startPeriod=2023-12-01&format=csvfile
- World Bank, Lending interest rate (FR.INR.LEND): https://data.worldbank.org/indicator/FR.INR.LEND
- World Bank, Deposit interest rate (FR.INR.DPST): https://data.worldbank.org/indicator/FR.INR.DPST
- World Bank API documentation: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation

BIS statistics must be attributed to the Bank for International Settlements. World Bank indicators should be attributed to the World Bank. This repository is not affiliated with or endorsed by either institution.

## Important interpretation notes
- `interest_rate` is a percentage rate as published by the source.
- `frequency` records the actual source frequency (daily/monthly/quarterly/annual where available).
- `observation_date` is the source reference period, not the download date.
- Missing observations are omitted; no values are invented.
- A 1,000-row / 100-country target is a validation goal, not a guarantee. The workflow reports actual coverage and fails the strict target check only when configured to do so.
