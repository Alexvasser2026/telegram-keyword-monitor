
name: Telegram keyword monitor

on:
  schedule:
    - cron: "2-59/5 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: telegram-keyword-monitor
  cancel-in-progress: false

jobs:
  check-messages:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Get project files
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install libraries
        run: python -m pip install -r requirements.txt

      - name: Check Telegram groups
        env:
          API_ID: ${{ secrets.API_ID }}
          API_HASH: ${{ secrets.API_HASH }}
          TELEGRAM_SESSION: ${{ secrets.TELEGRAM_SESSION }}
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          BOT_CHAT_ID: ${{ secrets.BOT_CHAT_ID }}
          STATE_ENCRYPTION_KEY: ${{ secrets.STATE_ENCRYPTION_KEY }}
          KEYWORDS: ${{ vars.KEYWORDS }}
          WATCH_GROUPS: ${{ vars.WATCH_GROUPS }}
        run: python monitor_once.py

      - name: Save encrypted checkpoint
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add state.enc
          if ! git diff --cached --quiet; then
            git commit -m "Update encrypted Telegram monitor checkpoint"
            git push
          fi
