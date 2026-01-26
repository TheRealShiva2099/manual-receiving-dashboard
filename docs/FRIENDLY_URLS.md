# Friendly URLs ("manual-receiving-dashboard") options

You can’t rename an IP address, but you *can* give people a nicer link.

## Option 1 (fastest, zero IT): use your laptop hostname
Sometimes your site DNS will resolve your laptop name automatically.

1) On your laptop, find hostname:
```bat
hostname
```
2) Coworker tries:
- `http://<hostname>:5000/`

If it works, congrats — you have a friendly-ish URL.

## Option 2 (still fast, per-user): hosts-file alias
On each coworker PC:
- Add a hosts entry mapping a friendly name to your laptop IP.

Example (requires admin):
- Edit: `C:\Windows\System32\drivers\etc\hosts`
- Add:
```
10.239.214.23 manual-receiving-dashboard
```
Then they can use:
- `http://manual-receiving-dashboard:5000/`

Downside: you must update it if your laptop IP changes.

## Option 3 (best “real” URL): request a DNS alias from site IT
Ask IT for a DNS A-record or CNAME:
- `manual-receiving-dashboard.s07377.us.wal-mart.com` → your host

For a laptop this is fragile because your IP may change.
Best with:
- a dedicated VM, or
- DHCP reservation / static IP

## Option 4 (nicer URL + no :5000): reverse proxy (IIS) on your host
Run IIS on your laptop and proxy:
- `http://localhost:5000` behind it

Then users can just use:
- `http://<hostname>/`

This is more setup, and you still need firewall rules for 80/443.

---

## Recommendation for “this week”
1) Try Option 1 (hostname) first.
2) If it fails, do Option 2 (hosts-file) for your immediate team.
3) For v3.5: move hosting to a VM and ask IT for Option 3.
