# `deploy/` — Production Deployment

Everything you need to run Vortex on a real server — systemd unit, nginx reverse-proxy, Kubernetes manifests, observability stack, load tests, chaos experiments.

## Layout

| Path              | What it is                                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| `nginx.conf`      | Reverse-proxy config: TLS termination, WebSocket upgrade, HTTP/2, static asset caching, HSTS.  |
| `vortex.service`  | systemd unit. Runs `/opt/vortex/.venv/bin/python run.py` under a dedicated `vortex` user with `ProtectSystem=strict`, `NoNewPrivileges=true`, and a `Restart=on-failure`. |
| `prometheus.yml`  | Top-level Prometheus scrape config (points at `:8000/metrics`).                                |
| `prometheus/`     | Alert rules — high-latency, WAF flood, peer-discovery degradation, disk pressure.              |
| `grafana/`        | Provisioning manifests + two dashboards (node overview, federation health).                    |
| `k8s/`            | Kubernetes manifests: namespace, configmap, secrets, HPA, blue-green deployment, PostgreSQL (HA), Redis, ingress. |
| `chaos/`          | [Chaos Mesh](https://chaos-mesh.org/) experiments — pod-kill, network-delay, network-partition, cpu-stress. |
| `loadtest/`       | k6 (`k6_load_test.js`) and Locust (`locustfile.py`) profiles. Targets rooms-create → send → fanout. |

## Typical flows

### Bare-metal / VM

```bash
# copy binary / source to /opt/vortex
sudo install -m 644 deploy/vortex.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vortex
sudo cp deploy/nginx.conf /etc/nginx/sites-available/vortex
sudo ln -s /etc/nginx/sites-available/vortex /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Kubernetes

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secrets.yaml           # review / template first
kubectl apply -f deploy/k8s/postgres.yaml          # or postgres-ha.yaml
kubectl apply -f deploy/k8s/redis.yaml
kubectl apply -f deploy/k8s/vortex.yaml
kubectl apply -f deploy/k8s/hpa.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

Blue/green cut-over via `blue-green.yaml` (changes the `version` label selector on the `vortex` Service).

### Observability

```bash
# Prometheus — scrapes Vortex + node-exporter + postgres-exporter
docker run -d --name prom -p 9090:9090 \
  -v $PWD/deploy/prometheus.yml:/etc/prometheus/prometheus.yml \
  -v $PWD/deploy/prometheus:/etc/prometheus/rules \
  prom/prometheus

# Grafana — auto-provisions dashboards from deploy/grafana/dashboards/
docker run -d --name graf -p 3000:3000 \
  -v $PWD/deploy/grafana/provisioning:/etc/grafana/provisioning \
  -v $PWD/deploy/grafana/dashboards:/var/lib/grafana/dashboards \
  grafana/grafana
```

### Load testing

```bash
# k6 — JS-based, better for long-running soak tests
k6 run deploy/loadtest/k6_load_test.js --vus 500 --duration 30m

# Locust — Python, better for quick exploration and headful runs
locust -f deploy/loadtest/locustfile.py --host=https://node.example.com
```

### Chaos

```bash
kubectl apply -f deploy/chaos/pod-kill.yaml         # random pod kill every 5m
kubectl apply -f deploy/chaos/network-partition.yaml
kubectl apply -f deploy/chaos/network-delay.yaml    # 200ms ± 50ms
kubectl apply -f deploy/chaos/cpu-stress.yaml       # 80% CPU for 10m
```

The chaos manifests are scoped to the `vortex` namespace only — do not apply them in a cluster shared with unrelated workloads.

## Hardening notes

- The nginx config forwards `X-Forwarded-For` — Vortex's WAF uses it for rate-limit buckets, so **do not** serve the node directly without a trust-relationship header rewrite.
- `vortex.service` uses `ReadWritePaths=/var/lib/vortex`; everything else on disk is read-only to the process.
- `configmap.yaml` contains no secrets — secrets live in `secrets.yaml` (templated; never commit filled-in versions).
- HPA scales on CPU **and** a custom metric `vortex_connected_peers` (exposed at `/metrics`).

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
