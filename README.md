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

A node that is not Ready gets a **delete** button in the node table (never a
control-plane node), for admins only. It force-deletes the pods still bound to the node,
removes its VolumeAttachments and deletes the Node, after asking. It does not
touch the machine itself or the mesh: a box that has left for good is also
removed on the hub with `xdctl mesh peer rm`.

Each app row ends in two switches, **private** and **public**: they attach
the app's `HTTPRoute` to, or detach it from, the internal Gateway (`aviary`)
and the NATed one (`aviary-nat`, aviary-deploy's `nat_gateway_ip`). System
entries have none. System entries are for admins (gitea site administrators and members of
the gitea team `ADMIN_TEAM`, default `aviary:admins`): anyone else sees them greyed out, with no link and no controls. Override the names with `GATEWAY_NAMESPACE`,
`PRIVATE_GATEWAY`, `PUBLIC_GATEWAY`.

With `CHAT_URL` set to an OpenAI-compatible API (the cluster's Ollama:
`http://ollama.aviary-ollama.svc:11434/v1`) the page gets a chat room beside
the fortune, IRC style: everyone on the page sees the same lines, each with
its author's name in front (`<bmath> ...`), and the model (`CHAT_MODEL`,
default `llama3`, speaking as `CHAT_NICK`) answers what is said. `/clear`
empties the room, `/stop` or Escape cuts a reply short. The name at the end
of the input line opens the model menu: switch the room to any model Ollama
has installed, or install another by name (`llama3.3:70b`,
`hf.co/user/repo:Q4_K_M`). The choice is kept in the `aviary-chat` ConfigMap
(`CHAT_STATE_CONFIGMAP`). The same ConfigMap's `briefing` key, if set, is background
handed to the model with every question (how sign-in works here, what each app
is for, who to ask): edit it with kubectl, no rebuild. The transcript is kept
in memory, so the app runs as a single gunicorn worker and a restart empties
the room. With no GPU in the cluster the room stays open and the model is marked away, IRC style.

The model can look things up while it answers. `kubernetes_get` reads the
cluster's API with a token for the `CHAT_SERVICE_ACCOUNT` ServiceAccount
(default `aviary-chat`, which aviary-deploy binds read-only, without Secrets),
never with this app's own rights. `http_get` fetches http/https URLs from
inside the cluster. Each lookup shows as a line in the reply.

Env: `CLUSTER_ISSUER` (default `ca-issuer`), `BASE_DOMAIN` (shown in the
header), `PORT` (8086).
