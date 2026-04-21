# `deploy/grafana/provisioning/` — Auto-provisioning

Grafana provisioning tree. When the provisioning directory is mounted at `/etc/grafana/provisioning` inside a Grafana container, it auto-creates datasources and dashboard folders on startup — no click-through config.

## Layout

```
provisioning/
├── datasources/
│   └── prometheus.yaml    ← registers the Prometheus datasource pointing at the URL from env
└── dashboards/
    └── dashboards.yaml    ← tells Grafana to import every JSON file under ../dashboards/
```

## Environment

The datasource YAML references `$PROMETHEUS_URL` so the same files work across local Docker and Kubernetes:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: ${PROMETHEUS_URL:-http://prometheus:9090}
    isDefault: true
```

## Running

See [`../README.md`](../README.md) for the full Grafana bring-up.

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
