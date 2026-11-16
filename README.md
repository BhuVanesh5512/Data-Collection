# Global Bank Interest Rates Dataset

Automated collection of official global interest-rate statistics using GitHub Actions.

## Coverage and sources
- **Central bank policy rates:** Bank for International Settlements (BIS) Central Bank Policy Rates, topic CBPOL. BIS documents long series for more than 40 advanced and emerging market economies, at daily and monthly frequency. Monthly observations are month-end values derived from daily data. [BIS CBPOL overview](https://data.bis.org/topics/CBPOL) · [BIS data documentation](https://www.bis.org/pages/statistics/cbpol-doc.pdf) · [BIS SDMX API](https://stats.bis.org/api-doc/v2/)
- **Lending rates:** World Bank WDI indicator `FR.INR.LEND`. [Indicator page](https://data.worldbank.org/indicator/FR.INR.LEND)
- **Deposit rates:** World Bank WDI indicator `FR.INR.DPST`. [Indicator page](https://data.worldbank.org/indicator/FR.INR.DPST)
- **World Bank API documentation:** https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation

## Date window
The workflow requests observations from 2023-12-01 through the current run date. The end date is calculated at runtime rather than hard-coded, so scheduled monthly runs continue to advance. The latest period available depends on each source's publication schedule.

## Output
`data/processed/global_bank_interest_rates.csv` is an observation-level dataset with canonical country/region name, original source country label, entity type (country or region), ISO-2 and ISO-3 codes where applicable, observation date, year, month, rate type, rate, frequency, source, series code, source URL, and retrieval metadata. Annual World Bank values use 1 January as a period label and have a blank month; monthly BIS values use the first day as the month label and retain the month number. Do not interpret these date labels as the exact day the rate changed.

## Monthly estimated panel
`data/processed/global_bank_interest_rates_monthly_estimates.csv` is a separate analytical convenience file. It contains clearly flagged monthly estimates for World Bank annual lending/deposit observations, using linear interpolation between annual values anchored at 1 July. It only interpolates between two observed annual values and does not extrapolate before the first or after the last anchor. Each estimated row includes `is_estimated`, `estimation_method`, anchor years, and anchor values. These rows are not official monthly observations and must not be mixed with the official CSV without filtering or labelling.

## Important limitations
BIS policy rates cover more than 40 economies, not 100+. World Bank lending/deposit indicators have broader country coverage but are annual. Consequently, 100+ countries and 1,000+ official observations are targets to assess against real source data, not guaranteed outcomes. The official CSV preserves source frequency. The separate estimated panel is for analysis only and does not turn annual source data into observed monthly data. Bank policy-rate records identify the monetary authority; World Bank lending/deposit indicators are country-level aggregates and cannot reliably be attributed to one named commercial bank. If an upstream API changes its schema, the workflow should fail visibly rather than silently generate incomplete data.

## Run
Open **Actions → Collect and verify global bank interest rates → Run workflow**. A monthly scheduled run is configured. The workflow collects official observations, independently verifies each official value against the source APIs, builds the separate estimated monthly panel, and commits the CSVs and verification reports only if collection and verification succeed.

## Attribution
Retain the original source references in the CSV. BIS statistics are subject to [BIS terms and citation guidance](https://data.bis.org/help/export). World Bank indicators should be attributed to the World Bank. This repository is not affiliated with or endorsed by either institution.
