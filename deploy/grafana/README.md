# `deploy/grafana/` — Grafana Provisioning & Dashboards

Self-contained Grafana setup. Drop the provisioning directory into a Grafana container and it will auto-load datasources and dashboards on startup.

## Layout

```
deploy/grafana/
├── provisioning/
│   ├── datasources/prometheus.yaml     ← Points at the Prometheus defined in ../prometheus.yml
│   └── dashboards/dashboards.yaml      ← Imports everything in ../dashboards/
└── dashboards/
    ├── node-overview.json              ← Per-node health, latency, throughput, peer count
    └── federation-health.json          ← Cross-node replication, trust decay, outbox depth
```

## Running

```bash
docker run -d --name graf -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=<your-password> \
  -v $PWD/deploy/grafana/provisioning:/etc/grafana/provisioning \
  -v $PWD/deploy/grafana/dashboards:/var/lib/grafana/dashboards \
  grafana/grafana
```

On first boot, Grafana reads `provisioning/`, creates the Prometheus datasource, and imports the dashboards — no clicking required.

## Dashboards

### `node-overview.json`

Panels:

- Request rate (req/s), split by route family.
- p50 / p95 / p99 latency per route family.
- Error rate (%) per route.
- WebSocket connection count (gauge + 1h rate).
- Peer discovery success rate per channel (UDP, controller, Solana, Redis).
- Uploads MB/s in / out.
- CPU + memory per pod (if scraping cadvisor).
- WAF verdicts per second — allow / challenge / block / tarpit.

### `federation-health.json`

Panels:

- Outbox depth per link (how many envelopes are waiting to ship).
- Replication lag per peer (seconds).
- Trust decay — live histogram of `last_checkin` ages across known peers.
- Cross-node integrity divergence — red if any peer's `code_hash` differs from its on-chain record.
- BMP mailbox polls per second (cover-traffic vs real).

## Editing

Dashboards are exported JSON — edit visually in Grafana, then "Share → Export → Save to file" back into this directory. Do not hand-edit the JSON (Grafana re-writes field order).

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
