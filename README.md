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

The rows of each list can be dragged into another order. The order is each
person's own, kept per gitea login in the `aviary-menu-order` ConfigMap
(`MENU_ORDER_CONFIGMAP`), so it follows them to any browser.

Every row has a **scale** button (`!` while containers lack requests or
limits, an arrow otherwise): the namespace's default requests and limits, and
the number of pods of each Deployment and StatefulSet (0 to `SCALE_MAX`,
default 10). A helm upgrade puts a chart's own number back.

CPU and memory read `now / max`: what an app is using, and its high-water mark
(the peak over `PEAK_WINDOW`, default `7d`, from Prometheus when
`PROMETHEUS_URL` is set; otherwise the most seen since this page started).

Each app row ends in two switches, **private** and **public**: they attach
the app's `HTTPRoute` to, or detach it from, the internal Gateway (`aviary`)
and the NATed one (`aviary-nat`, aviary-deploy's `nat_gateway_ip`). System
entries have none. System entries are for admins (gitea site administrators and members of
the gitea team `ADMIN_TEAM`, default `aviary:admins`): anyone else sees them greyed out, with no link and no controls. Override the names with `GATEWAY_NAMESPACE`,
`PRIVATE_GATEWAY`, `PUBLIC_GATEWAY`.

The box beside the fortune is the **whiteboard**: a chat room over a canvas.
Everyone on the page sees the same lines and the same drawing. The pencil
button turns the pointer into a pen (strokes are coloured per person);
`/erase` wipes the drawing, `/clear` the whole board. Both are kept in
memory, like the lines.

**Claude** is optional. With `ANTHROPIC_API_KEY` set it is one more entry in
the room's model menu (`claude`; `CLAUDE_MODEL`, default `claude-opus-5-5`;
`CLAUDE_EFFORT`, default `medium`), reached through Anthropic's SDK: choosing
it switches the room to it instead of the cluster's model, for everyone, like
any other switch. It needs no GPU, so it is never away, and it has the same
two read-only lookups. Every reply is billed to that key, and what is said
in the room while it is chosen is sent to Anthropic's API; the pod needs a
way out to `api.anthropic.com`.

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
