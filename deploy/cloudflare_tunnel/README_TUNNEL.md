# Cloudflare Tunnel (Public HTTPS from Laptop)

This setup exposes your local OVC backend to the public internet over HTTPS via Cloudflare Tunnel, without router port forwarding.

## 1) Install cloudflared

macOS (Homebrew):

```bash
brew install cloudflared
```

## 2) Authenticate cloudflared

```bash
cloudflared tunnel login
```

This opens Cloudflare in browser and stores your cert locally.

## 3) Create tunnel and credentials

```bash
cloudflared tunnel create ovc-laptop
```

Save the generated:
- Tunnel ID
- credentials JSON path

## 4) Create DNS hostname for tunnel

```bash
cloudflared tunnel route dns ovc-laptop <YOUR_HOSTNAME>
```

Example: `notes.example.com`

## 5) Prepare tunnel config

1. Copy template:

```bash
cp deploy/cloudflare_tunnel/config.yml.template ~/cloudflared/ovc-config.yml
```

2. Edit `~/cloudflared/ovc-config.yml`:
- replace `<TUNNEL_ID>`
- set correct `credentials-file`
- replace `<YOUR_HOSTNAME>`

## 6) Configure environment

In `.env`:

```env
PUBLIC_BASE_URL=https://<YOUR_HOSTNAME>
CORS_ORIGINS=["https://<YOUR_HOSTNAME>","http://127.0.0.1:8000"]
COOKIE_DOMAIN=<YOUR_HOSTNAME>
COOKIE_SECURE=true
CLOUDFLARED_CONFIG_PATH=/absolute/path/to/ovc-config.yml
```

## 7) Start backend and tunnel

Terminal 1:

```bash
./deploy/cloudflare_tunnel/start_public_server.sh
```

Terminal 2:

```bash
./deploy/cloudflare_tunnel/start_tunnel.sh
```

## 8) Verify health

```bash
./deploy/cloudflare_tunnel/verify_public.sh
```

Expected:
- local `/healthz` returns `{"ok": true}`
- public `https://<YOUR_HOSTNAME>/healthz` returns `{"ok": true}`

## Notes

- Do not commit tunnel credentials JSON.
- For tunnel-only mode keep backend bound to `127.0.0.1` (default in `start_public_server.sh`).
- For LAN testing only: `HOST=0.0.0.0 ./deploy/cloudflare_tunnel/start_public_server.sh`

## Quick mode (no domain, temporary URL)

If you don't have a domain yet, use `trycloudflare`:

Terminal 1:

```bash
./deploy/cloudflare_tunnel/start_public_server.sh
```

Terminal 2:

```bash
QUICK_TUNNEL=true ./deploy/cloudflare_tunnel/start_tunnel.sh
```

Cloudflared will print a temporary URL like:
`https://something.trycloudflare.com`

Important:
- URL changes on every restart.
- For quick mode keep `COOKIE_DOMAIN=` empty in `.env`.
