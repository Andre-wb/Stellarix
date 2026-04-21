# `app/benchmarks/` — Synthetic Benchmarks

Synthetic load + crypto micro-benchmarks for the node backend. Standalone scripts — not part of pytest.

## Files

| File                | Role                                                                          |
| ------------------- | ----------------------------------------------------------------------------- |
| `run_benchmarks.py` | Entry point. Parses CLI flags, wires the selected benchmarks into `pyperf`-compatible runs, writes a `results.json` alongside.  |

## Running

```bash
cd /Users/borismaltsev/RustroverProjects/Vortex
python -m app.benchmarks.run_benchmarks --all
python -m app.benchmarks.run_benchmarks --only crypto
python -m app.benchmarks.run_benchmarks --only message-roundtrip --iterations 1000
```

## What's measured

- **Crypto primitives**: AES-256-GCM seal/unseal throughput, X25519 keygen/ECDH rate, BLAKE3 MB/s, Argon2id hashes/sec at the configured parameters.
- **Message round-trip**: client send → node receive → node ack, isolated from network — runs in-process against a test client.
- **BMP hot path**: mailbox ID derivation throughput, cover-traffic polling latency.
- **Federation**: envelope pack + sign + verify cycle, single-peer fan-out.
- **Upload**: chunk hashing throughput, finalise latency for 1GB synthetic file.

## What it's NOT

- **Not a load test.** For long-running realistic load use `../../deploy/loadtest/k6_load_test.js` or `locustfile.py`.
- **Not a correctness test.** The benchmarks assume the code is already correct (pytest handles that).
- **Not production tracing.** Use Prometheus + Grafana (`../../deploy/grafana/dashboards/`) for live data.

## Results layout

`results.json` is a flat list of records:

```json
[
  {"name": "aes_gcm_seal_1kb", "mean_ns": 3400, "stdev_ns": 120, "iterations": 10000},
  {"name": "x25519_ecdh",      "mean_ns": 19000, "stdev_ns": 900,  "iterations": 5000},
  ...
]
```

Comparing across commits is left to the reader — diff `results.json` files, no CI harness bundled.

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
