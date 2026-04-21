# `deploy/loadtest/` — Load Testing Profiles

Two load-test harnesses with different trade-offs:

| Tool   | File                 | Best for                                                 |
| ------ | -------------------- | -------------------------------------------------------- |
| **k6** | `k6_load_test.js`    | Long-running soak tests, JS ergonomics, rich metrics.    |
| **Locust** | `locustfile.py`  | Quick experiments, headful debugging, Python fixtures.   |

## `k6_load_test.js`

Scenario: login → create room → send 100 messages → read history → upload 1MB file.

```bash
# Soak test
k6 run deploy/loadtest/k6_load_test.js --vus 500 --duration 30m

# Quick smoke
k6 run deploy/loadtest/k6_load_test.js --vus 10 --iterations 100

# Ramp profile baked into the script
k6 run deploy/loadtest/k6_load_test.js
```

Environment variables the script reads:

| Var           | Purpose                                                       |
| ------------- | ------------------------------------------------------------- |
| `BASE_URL`    | Target node (default `https://localhost:8000`).               |
| `TLS_INSECURE`| `1` to skip cert verification (self-signed dev nodes).        |
| `USERS_POOL`  | Number of pre-provisioned accounts to rotate through.         |

Outputs: stdout summary, optional InfluxDB / Prometheus pushgateway via `--out` flag.

## `locustfile.py`

Interactive or headless:

```bash
# Headful — open http://localhost:8089
locust -f deploy/loadtest/locustfile.py --host https://localhost:8000

# Headless, fixed spawn
locust -f deploy/loadtest/locustfile.py --host https://localhost:8000 \
       --users 100 --spawn-rate 5 --run-time 10m --headless
```

Tasks are weighted:

| Weight | Task                    |
| ------ | ----------------------- |
| 10     | GET rooms list          |
| 5      | POST message            |
| 3      | GET message history     |
| 1      | Upload file             |
| 1      | Join / leave voice room |

Edit `locustfile.py` to adjust weights or add tasks — the weights reflect a realistic chat workload.

## SLOs to watch

| Metric                                  | Target       |
| --------------------------------------- | ------------ |
| p99 latency, `POST /api/chat/messages`  | < 250 ms     |
| Error rate                              | < 0.1 %      |
| WebSocket reconnect rate under chaos    | < 1 /min/vu  |
| Uploads / sec at 1 MB                   | ≥ 50 / pod   |

## Don't point at production without cross-checks

Both tools can easily saturate a real server. Always:

1. Run against a dedicated test environment.
2. Coordinate with on-call if sharing infra.
3. Start at 10% of target VUs, observe, then ramp.

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
