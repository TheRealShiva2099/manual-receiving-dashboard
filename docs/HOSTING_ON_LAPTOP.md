# Hosting ATC from your laptop (temporary)

This is the fastest way to make the dashboard reachable to others in your building.

**Downside:** if your laptop sleeps, disconnects, reboots, or changes networks, the dashboard goes down.

---

## 1) Start ATC in LAN host mode
Run:
- `Step 2 - START ATC (LAN Host).bat`

This sets:
- `ATC_HOST=0.0.0.0`
- `ATC_PORT=5000`

So other devices on your LAN can reach the Flask server.

---

## 2) Find your IP address
Open Command Prompt and run:

```bat
ipconfig
```

Look for your active adapter (Ethernet/Wi‑Fi) and copy the **IPv4 Address**.

Example:
- `10.23.45.67`

Users will go to:
- `http://10.23.45.67:5000/`

---

## 3) Allow inbound firewall traffic (port 5000)
You need Windows Firewall to allow inbound TCP 5000.

### Option A: GUI
Windows Defender Firewall → Inbound Rules → New Rule → Port → TCP 5000 → Allow.

### Option B: command line (run in an elevated CMD)
```bat
netsh advfirewall firewall add rule name="Manual Receiving ATC (TCP 5000)" dir=in action=allow protocol=TCP localport=5000
```

To remove it later:
```bat
netsh advfirewall firewall delete rule name="Manual Receiving ATC (TCP 5000)"
```

---

## 4) Keep the host alive
- Disable sleep while plugged in
- Keep on the same network
- Prefer Ethernet if possible

---

## 5) Quick troubleshooting
- From another PC, test connectivity:
  - `ping <your-ip>`
- If ping works but site doesn’t load:
  - firewall rule missing
  - wrong IP
  - you’re on VPN / different subnet

---

## 6) Security warning
Anyone who can reach your laptop on port 5000 can view the dashboard.
To reduce risk:
- restrict the firewall rule scope to your site subnet if possible
- move to a dedicated VM/host ASAP

