# `deploy/k8s/` — Kubernetes Manifests

Opinionated manifest set for deploying Vortex on a Kubernetes cluster. Includes HA PostgreSQL, Redis pubsub, HPA, blue-green cutover support, ingress.

## Files

| File               | Kind                    | Role                                                             |
| ------------------ | ----------------------- | ---------------------------------------------------------------- |
| `namespace.yaml`   | Namespace               | Creates `vortex` with pod-security-admission labels.             |
| `configmap.yaml`   | ConfigMap               | Non-secret config (ports, feature flags, controller pubkey).    |
| `secrets.yaml`     | Secret (templated)      | JWT / CSRF / DB / VAPID / FCM / APNs secrets. **Never commit filled values.** |
| `postgres.yaml`    | Deployment + Service    | Single-replica PostgreSQL for small deployments.                |
| `postgres-ha.yaml` | StatefulSet + Services  | HA PostgreSQL with streaming replication + pgpool frontend.     |
| `redis.yaml`       | Deployment + Service    | Redis for cross-pod peer-discovery pubsub.                      |
| `vortex.yaml`      | Deployment + Service    | The node pod itself. Readiness + liveness probes wired to `/healthz` + `/readyz`. |
| `hpa.yaml`         | HorizontalPodAutoscaler | Scales `vortex` deployment on CPU **and** custom metric `vortex_connected_peers`. |
| `blue-green.yaml`  | Service                 | Version-labelled service used for zero-downtime cutover.         |
| `ingress.yaml`     | Ingress                 | TLS termination + WebSocket upgrade annotations.                 |

## Typical apply order

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
# review and template secrets.yaml first
kubectl apply -f secrets.yaml
kubectl apply -f postgres.yaml            # or postgres-ha.yaml
kubectl apply -f redis.yaml
kubectl apply -f vortex.yaml
kubectl apply -f hpa.yaml
kubectl apply -f ingress.yaml
```

## Blue-green cutover

`vortex.yaml` ships two Deployments at once (`vortex-blue`, `vortex-green`). The `Service` in `blue-green.yaml` selects on `version: <active>`. To cut over:

```bash
# Deploy new version to the idle colour
kubectl apply -f vortex.yaml   # updates the idle Deployment
# Wait until rollout is Healthy
kubectl rollout status deployment/vortex-green -n vortex
# Flip the service
kubectl patch service vortex -n vortex \
  --patch '{"spec":{"selector":{"version":"green"}}}'
# Validate; rollback by patching back to blue if needed.
```

## Scaling

- `hpa.yaml` scales between 2 and 20 replicas.
- CPU target: 70%. Custom metric target: 500 connected peers per pod.
- **WebSocket stickiness** handled at the ingress (`nginx.ingress.kubernetes.io/affinity: cookie`) so a peer's long-lived WS doesn't jump pods.

## Secrets

The `secrets.yaml` file is checked in **empty** (placeholders). Operators template it locally from a password manager or their CI secret store:

```bash
envsubst < secrets.yaml | kubectl apply -f -
```

Never commit a filled-in copy.

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
