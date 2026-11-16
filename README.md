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

Each app row ends in two switches, **private** and **public**: they attach
the app's `HTTPRoute` to, or detach it from, the internal Gateway (`aviary`)
and the NATed one (`aviary-nat`, aviary-deploy's `nat_gateway_ip`). System
entries have none. Override the names with `GATEWAY_NAMESPACE`,
`PRIVATE_GATEWAY`, `PUBLIC_GATEWAY`.

With `CHAT_URL` set to an OpenAI-compatible API (the cluster's Ollama:
`http://ollama.aviary-ollama.svc:11434/v1`) the page gets a chat window in the
bottom-right corner, talking to `CHAT_MODEL` (default `llama3`). The browser
only talks to this app; `/api/chat` relays to the model and streams the reply.

Env: `CLUSTER_ISSUER` (default `ca-issuer`), `BASE_DOMAIN` (shown in the
header), `PORT` (8086).
