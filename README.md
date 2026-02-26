# redfin-tracker

Automated daily Redfin price tracker using [ScrapeServ](https://github.com/goodreasonai/ScrapeServ).

Runs every day at **3 AM UTC** via GitHub Actions and saves the Redfin Estimate price to `redfin_price_history.csv`.

## How it works

1. GitHub Actions spins up a ScrapeServ Docker container.
2. `scripts/redfin_tracker.py` sends the Redfin URL to ScrapeServ.
3. ScrapeServ launches a real Firefox browser, loads the page, and returns the HTML.
4. The script extracts the Redfin Estimate price and appends it with a timestamp to `redfin_price_history.csv`.
5. The updated CSV is automatically committed back to this repo.

## Configuration

To track a different property, update the `REDFIN_URL` environment variable in `.github/workflows/redfin_scraper.yml`.

## Manual trigger

Go to **Actions → Daily Redfin Price Tracker → Run workflow** to scrape on demand.
