# `deploy/grafana/dashboards/` — Dashboard JSON

Pre-built Grafana dashboards auto-imported at boot via `../provisioning/dashboards/dashboards.yaml`.

## Files

| File                        | Focus                                                   |
| --------------------------- | ------------------------------------------------------- |
| `node-overview.json`        | Per-node health, latency, throughput, peer count, WAF verdicts. |
| `federation-health.json`    | Cross-node replication, trust decay, outbox depth, BMP cover traffic vs real. |

See [`../README.md`](../README.md) for panel-level detail.

## Editing

Edit visually inside Grafana, then "Share → Export → Save to file" back into this folder. **Don't hand-edit** — Grafana rewrites field ordering and diffs become noisy.

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
