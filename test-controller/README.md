# test-controller

Standalone mock Vortex controller for testing the wizard and clients.
**Zero dependencies on the main project at runtime.** The Python source
imports only `fastapi`, `uvicorn`, and `cryptography` — no `app/`, no
`vortex_controller/`, no database.

## Run from source

```bash
cd test-controller
python server.py                    # listens on http://127.0.0.1:8800
python server.py --port 9000        # custom port
python server.py --host 0.0.0.0     # accept connections from LAN
python server.py --tunnel           # also open a cloudflared tunnel + print public URL
python server.py --print-key        # print the generated pubkey and exit
```

Every launch generates a **fresh** Ed25519 signing key — so restart = new
pubkey. That's intentional for testing: no state leaks between runs.

### --tunnel — test the Vortex wizard over the real internet

The `--tunnel` flag spawns `cloudflared` in the background and prints
the issued `*.trycloudflare.com` URL — which you can paste directly
into the Vortex wizard (Custom mode) to exercise the **exact same code
path** as a production `vortexx.sol` deployment, minus the domain.

Output looks like:

```
─── vortex test-controller test-0.1.0 ───
  signing pubkey:  f09bb55fb27020a847a090a2f0c928fed2afd803a71761d6a84864eb365fa025
  listening on:    http://127.0.0.1:8800
  public URL:      https://ballot-kidney-roof-surveillance.trycloudflare.com

  For the Vortex wizard (Custom mode):
    CONTROLLER_URL    = https://ballot-kidney-roof-surveillance.trycloudflare.com
    CONTROLLER_PUBKEY = f09bb55fb27020a847a090a2f0c928fed2afd803a71761d6a84864eb365fa025
```

Copy those two lines into the wizard's Custom mode fields and click
through setup — everything behaves the same as against a real
controller. Ctrl+C on this terminal tears down both the server and the
tunnel cleanly.

Requires `cloudflared` installed (`brew install cloudflared` on macOS —
the binary also searches `/opt/homebrew/bin`, `/usr/local/bin`,
`/snap/bin`, etc. in case your shell's PATH is trimmed).

## Build a standalone binary

```bash
pip install pyinstaller               # if not already
pyinstaller test-controller.spec --clean --noconfirm
# → dist/test-controller  (~15 MB single file)

./dist/test-controller                # same CLI, no Python needed
```

The binary is self-contained — copy it to any Mac (or build on Linux /
Windows from the same spec) and run.

## What it serves

| Endpoint | Signed envelope | Purpose |
|----------|:---------------:|---------|
| `GET /` | — | plain-text banner + pubkey + endpoint list |
| `GET /v1/health` | — | `status` / `version` / `pubkey` / `stats` |
| `GET /v1/integrity` | — | mock `verified` report |
| `GET /v1/treasury` | — | treasury wallet + fee schedule |
| `GET /v1/entries` | ✓ | 5 bootstrap URLs (tunnel/tor/ipfs/direct) |
| `GET /v1/mirrors` | ✓ | 6 mirrors with varied health |
| `GET /v1/mirrors/health` | — | probe results |
| `GET /v1/nodes/random?count=N` | ✓ | up to 8 fake peers |
| `GET /v1/nodes/lookup/{pubkey}` | ✓ | one peer or 404 |
| `GET /v2/record/{domain}/URL` | — | Bonfida-SNS-stub — points back at self |
| `GET /v2/record/{domain}/TXT` | — | same, pubkey record |

Signatures use the same canonical-JSON scheme (keys sorted, no spaces)
as the real controller, so client-side verification passes against the
`pubkey` printed in `/v1/health`.

## Quick verification

```bash
./dist/test-controller --port 8800 &
curl -s http://127.0.0.1:8800/v1/health | jq
curl -s http://127.0.0.1:8800/v1/nodes/random?count=3 | jq
```

## Use from the wizard

In your wizard `.env` (or during first-run):

```
CONTROLLER_URL=http://127.0.0.1:8800
CONTROLLER_PUBKEY=<paste from /v1/health.pubkey>
```

Or — if the wizard auto-resolves `vortexx.sol` via Bonfida — route the
Bonfida API at this binary: it implements the two record endpoints too.
Either set `BONFIDA_API_BASE=http://127.0.0.1:8800` (if the wizard reads
that env) or edit `/etc/hosts`:

```
127.0.0.1 sns-api.bonfida.com
```

…and restart the wizard.

## Cleanup

Nothing persists on disk — stopping the process is a clean shutdown.
