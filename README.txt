================================================================================
  MANUAL RECEIVING ATC - US-07377
================================================================================

What this is
------------
This tool monitors BigQuery for Manual Receiving events for facility US-07377 and:
- Sends desktop notifications
- Runs a local dashboard at: http://localhost:5000
- Keeps a 24-hour local event history + CSV export

This is designed to be “Westly-style”: runs locally on your laptop. No server.

================================================================================
  REQUIREMENTS (YOU MUST HAVE THESE)
================================================================================

1) Python 3.8+
   - Make sure Python is on PATH

2) Google Cloud SDK (bq CLI)
   - Install + authenticate:
     - gcloud auth login
     - gcloud auth application-default login

3) BigQuery access
   - Read access to the required Supply Chain datasets

================================================================================
  INSTALL / RUN (3 STEPS)
================================================================================

Step 1) Install
  - Double-click: "Step 1 - INSTALL.bat"

Step 2) Start (silent)
  - Double-click: "Step 2 - START ATC (Silent).bat"
  - No window appears by design.

Step 3) Open dashboard
  - Go to: http://localhost:5000
  - Bookmark it.

================================================================================
  CONFIG
================================================================================

Edit: atc_config.json

Key settings:
- monitoring.facility_id = US-07377
- monitoring.timezone = America/New_York
- monitoring.overflow_locations = ["EOF", "WOF"]
- dashboard.tableau_url = (optional)

================================================================================
  TROUBLESHOOTING
================================================================================

If something doesn’t work:
1) Run: "Step 2 - START ATC DEBUG.bat" (shows console logs)
2) Confirm bq works:
   - bq --version
   - bq ls --project_id=wmt-edw-prod
3) See DEBUGGING_GUIDE.md

================================================================================
