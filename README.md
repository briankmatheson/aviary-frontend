# aviary-frontend

The Aviary landing page: a menu of every app the shared Gateway serves
(read live from the cluster's `HTTPRoute`s), the cluster CA at `/ca.crt`,
and a node table.

```
make push                               # briankmatheson/aviary-frontend:<git describe>
make push REGISTRY=registry.example.net # your own registry
make push TAG=1.0.0
```

On a box running xdebbie, `REGISTRY` defaults to `registry.<mesh domain>`
from `/etc/xdebbie/xdebbied.toml`.

Deployed by [aviary-deploy](https://github.com/briankmatheson/aviary-deploy)
(`apps/aviary-frontend.tf`, variable `aviary_frontend_image`): ServiceAccount
with read access to httproutes, gateways, nodes, the ClusterIssuer and its CA
secret.

Env: `CLUSTER_ISSUER` (default `ca-issuer`), `BASE_DOMAIN` (shown in the
header), `PORT` (8086).
