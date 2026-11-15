# Global Bank Interest Rates Dataset

Automated collection of official global interest-rate statistics using GitHub Actions.

## Coverage and sources
- **Central bank policy rates:** Bank for International Settlements (BIS) Central Bank Policy Rates, topic CBPOL. BIS documents long series for more than 40 advanced and emerging market economies, at daily and monthly frequency. Monthly observations are month-end values derived from daily data. [BIS CBPOL overview](https://data.bis.org/topics/CBPOL) · [BIS data documentation](https://www.bis.org/pages/statistics/cbpol-doc.pdf) · [BIS SDMX API](https://stats.bis.org/api-doc/v2/)
- **Lending rates:** World Bank WDI indicator `FR.INR.LEND`. [Indicator page](https://data.worldbank.org/indicator/FR.INR.LEND)
- **Deposit rates:** World Bank WDI indicator `FR.INR.DPST`. [Indicator page](https://data.worldbank.org/indicator/FR.INR.DPST)
- **World Bank API documentation:** https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation

## Date window
The workflow requests 2023-12-01 through 2026-11-15. The latest period available depends on each source's publication schedule; November 2026 may be incomplete or not yet published.

## Output
`data/processed/global_bank_interest_rates.csv` is an observation-level dataset with country, ISO3, observation date, rate type, rate, frequency, source, series code, source URL, and retrieval metadata.

## Important limitations
BIS policy rates cover more than 40 economies, not 100+. World Bank lending/deposit indicators have broader country coverage but are annual. Consequently, 100+ countries and 1,000+ observations are targets to assess against the real source data, not guaranteed outcomes. Annual and daily/monthly series remain at their original frequency. No interpolation, monthly upsampling, or invented values are permitted. If an upstream API changes its schema, the workflow should fail visibly rather than silently generate incomplete data.

## Run
Open **Actions → Collect global bank interest rates → Run workflow**. A monthly scheduled run is configured. The workflow commits the refreshed CSV when collection succeeds.

## Attribution
Retain the original source references in the CSV. BIS statistics are subject to [BIS terms and citation guidance](https://data.bis.org/help/export). World Bank indicators should be attributed to the World Bank. This repository is not affiliated with or endorsed by either institution.
