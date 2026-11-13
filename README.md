# aviary-frontend

The Aviary landing page: a menu of every app the shared Gateway serves
(read live from the cluster's `HTTPRoute`s), the cluster CA at `/ca.crt`,
and a node table.

```
make push            # build + push registry.mesh.harlem.bmath.nyc/aviary-frontend:<git describe>
make push TAG=1.0.0
```

Deployed by [aviary-deploy](https://github.com/briankmatheson/aviary-deploy)
(`apps/aviary-frontend.tf`): ServiceAccount with read access to httproutes,
gateways, nodes, the ClusterIssuer and its CA secret.

Env: `CLUSTER_ISSUER` (default `ca-issuer`), `BASE_DOMAIN` (shown in the
header), `PORT` (8086).
