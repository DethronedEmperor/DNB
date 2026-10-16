name: 24/7 Gaming RSS Aggregator

on:
  schedule:
    # Runs automatically every 15 minutes, 24/7
    - cron: '*/15 * * * *'
  workflow_dispatch: # Allows manual trigger button for testing

jobs:
  run-aggregator:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install Dependencies
        run: pip install requests

      - name: Run News Bot
        run: python news_bot.py

      - name: Commit Updated History
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add posted_links.txt
          git commit -m "Update posted articles history" || exit 0
          git push
