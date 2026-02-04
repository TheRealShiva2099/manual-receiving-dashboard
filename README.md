# Manual Receiving Dashboard

Local monitoring and dashboard app for manual receiving events.

## Setup on Another PC

1. Install prerequisites:
   - Python 3.8+  
   - Google Cloud SDK (for `bq` CLI) and `gcloud auth application-default login`
2. Clone the repo:
   - `git clone https://github.com/TheRealShiva2099/manual-receiving-dashboard.git`
3. Create your local config:
   - Copy `atc_config.example.json` to `atc_config.json`
   - Fill in BigQuery settings, Teams webhooks, and email settings
4. Install dependencies:
   - `pip install -r requirements_atc.txt`
5. Start the app:
   - Run `windows_batch_files/v4/Step 2 - START ATC (Silent).bat`
   - Or run `windows_batch_files/v4/Step 2 - START ATC DEBUG.bat` for console output

### LAN Access

The dashboard is reachable at:
`http://<host-ip>:<port>`

The IP will be different per machine. The port is configurable in the app config. Share the host machine’s IP/port with other users on the same network.
