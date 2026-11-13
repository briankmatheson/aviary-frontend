"""Aviary landing page.

A menu of everything the shared Gateway serves, built from the cluster's
HTTPRoutes (so a new vhost in aviary-deploy's local.vhosts shows up here
without touching this app), plus the cluster CA for download and a node
table.

Env:
  CLUSTER_ISSUER  cert-manager ClusterIssuer whose CA secret /ca serves
                  (default ca-issuer; a selfsigned issuer has no CA)
  PORT            listen port (default 8086)
"""
import html
import os
import re
import threading
import time

from bottle import Bottle, response, static_file
from kubernetes import client, config

app = Bottle()
HERE = os.path.dirname(os.path.abspath(__file__))
ISSUER = os.environ.get("CLUSTER_ISSUER", "ca-issuer")

# What each app is for. Keyed by the first label of the hostname; anything
# not listed still appears, just without a blurb.
BLURBS = {
    "argo": "Continuous delivery (Argo CD)",
    "drone": "Continuous integration",
    "gitea": "Source code management",
    "harbor": "Container image registry",
    "grafana": "Metrics visualisation and alerting",
    "headlamp": "Kubernetes UI",
    "postgres-ui": "Postgres operator UI",
    "rustpad": "Shared text editor",
    "bash": "In-cluster shell",
    "velero": "Backup and restore",
    "jupyterhub": "Interactive notebooks",
    "mlflow": "Machine learning lifecycle",
    "qdrant": "Vector database",
    "minio": "Object store",
    "jitsi": "Video conferencing",
}

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def routes():
    """[(host, namespace, service, port, gateway_ip)] for every HTTPRoute."""
    custom = client.CustomObjectsApi()
    out = []
    gws = {}
    for gw in custom.list_cluster_custom_object(
        "gateway.networking.k8s.io", "v1", "gateways"
    ).get("items", []):
        addrs = [a["value"] for a in gw.get("status", {}).get("addresses", [])]
        gws[(gw["metadata"]["namespace"], gw["metadata"]["name"])] = addrs[0] if addrs else ""
    for r in custom.list_cluster_custom_object(
        "gateway.networking.k8s.io", "v1", "httproutes"
    ).get("items", []):
        spec = r.get("spec", {})
        hosts = spec.get("hostnames", [])
        if not hosts:
            continue
        ns = r["metadata"]["namespace"]
        ip = ""
        for p in spec.get("parentRefs", []):
            ip = gws.get((p.get("namespace", ns), p.get("name")), "") or ip
        for rule in spec.get("rules", []):
            # The https-redirect route has filters and no backends; skip it.
            for b in rule.get("backendRefs", []):
                for h in hosts:
                    out.append((h, b.get("namespace", ns), b.get("name", ""), b.get("port", ""), ip))
    # one line per host
    seen, uniq = set(), []
    for row in sorted(out):
        if row[0] not in seen:
            seen.add(row[0])
            uniq.append(row)
    return uniq


def nodes():
    v1 = client.CoreV1Api()
    usage = {}
    try:
        for n in client.CustomObjectsApi().list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "nodes"
        ).get("items", []):
            usage[n["metadata"]["name"]] = n["usage"]
    except Exception:
        pass  # metrics-server optional
    rows = []
    for n in v1.list_node().items:
        ready = next((c.status for c in n.status.conditions if c.type == "Ready"), "Unknown")
        roles = ",".join(
            k.split("/", 1)[1] for k in n.metadata.labels if k.startswith("node-role.kubernetes.io/")
        ) or "worker"
        u = usage.get(n.metadata.name)
        cpu = mem = "-"
        if u:
            cpu = "%d%%" % (100 * _q(u["cpu"]) / _q(n.status.allocatable["cpu"]))
            mem = "%d%%" % (100 * _q(u["memory"]) / _q(n.status.allocatable["memory"]))
        rows.append((n.metadata.name, roles, ready, n.status.node_info.kubelet_version, cpu, mem))
    return rows


_SUFFIX = {"n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "K": 1e3, "M": 1e6, "G": 1e9}


def _q(s):
    m = re.fullmatch(r"([0-9.]+)([a-zA-Z]*)", str(s))
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1)


def ca_pem():
    cm = client.CustomObjectsApi()
    issuer = cm.get_cluster_custom_object("cert-manager.io", "v1", "clusterissuers", ISSUER)
    name = issuer["spec"].get("ca", {}).get("secretName")
    if not name:
        return None
    sec = client.CoreV1Api().read_namespaced_secret(name, "cert-manager")
    import base64
    data = sec.data.get("ca.crt") or sec.data.get("tls.crt")
    return base64.b64decode(data).decode() if data else None


def snapshot():
    with _lock:
        if time.time() - _cache["at"] > 15:
            _cache["data"] = {"routes": routes(), "nodes": nodes()}
            _cache["at"] = time.time()
        return _cache["data"]


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Aviary</title>
<link rel="icon" href="/favicon.ico">
<style>
 body {{ font: 16px/1.4 system-ui, sans-serif; margin: 0; color: #222;
        background-color: #fbfbf8;
        background-image:
          linear-gradient(rgba(70,130,180,.28) 1px, transparent 1px),
          linear-gradient(90deg, rgba(70,130,180,.28) 1px, transparent 1px),
          linear-gradient(rgba(70,130,180,.10) 1px, transparent 1px),
          linear-gradient(90deg, rgba(70,130,180,.10) 1px, transparent 1px);
        background-size: 100px 100px, 100px 100px, 20px 20px, 20px 20px; }}
 main {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 64px; }}
 nav {{ font-size: 14px; margin-bottom: 8px; }}
 nav a {{ color: #1a4d8f; text-decoration: none; padding: 4px 10px; background: rgba(255,255,255,.85);
         border: 1px solid #d8dde5; border-radius: 6px; }}
 nav a:hover {{ background: #fffbe6; }}
 h1 {{ font-size: 56px; margin: 0 0 4px; letter-spacing: -1px; }}
 h1 small {{ font-size: 16px; color: #666; margin-left: 12px; letter-spacing: 0; }}
 h2 {{ margin: 36px 0 8px; font-size: 18px; color: #555; text-transform: uppercase; letter-spacing: 1px; }}
 ul.menu {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
 ul.menu li a {{ display: block; padding: 14px 16px; background: rgba(255,255,255,.85); border-radius: 8px;
                 text-decoration: none; color: #1a4d8f; font-size: 22px; box-shadow: 0 1px 2px rgba(0,0,0,.08); }}
 ul.menu li a:hover {{ background: #fffbe6; }}
 ul.menu li a small {{ display: block; font-size: 13px; color: #666; margin-top: 2px; }}
 table {{ border-collapse: collapse; background: rgba(255,255,255,.85); width: 100%; font-size: 14px; }}
 th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #e3e3df; }}
 th {{ color: #666; font-weight: 600; }}
 pre {{ background: rgba(255,255,255,.85); padding: 12px; overflow-x: auto; font-size: 13px; }}
 .ok {{ color: #1b7f3b; }} .bad {{ color: #b00020; }}
 footer {{ margin-top: 48px; color: #888; font-size: 13px; }}
</style></head><body><main>
<nav><a href="/ca.crt" download="ca.crt" title="Cluster CA: trust this to stop the browser warnings">ca.crt</a></nav>
<h1>Aviary<small>{host}</small></h1>
<h2>Apps</h2>
<ul class="menu">{menu}</ul>
<h2>Cluster</h2>
<table><tr><th>Node</th><th>Role</th><th>Ready</th><th>Kubelet</th><th>CPU</th><th>Memory</th></tr>{nodes}</table>
<h2>/etc/hosts</h2>
<p>If your resolver does not know these names:</p>
<pre>{hosts}</pre>
<footer>Served by {me}</footer>
</main></body></html>
"""


@app.route("/")
def index():
    d = snapshot()
    me = os.environ.get("HOSTNAME", "")
    items = []
    for host, ns, svc, port, ip in d["routes"]:
        if svc == "aviary-frontend":
            continue  # that's us
        label = host.split(".", 1)[0]
        blurb = BLURBS.get(label, f"{ns}/{svc}:{port}")
        items.append(
            f'<li><a href="https://{html.escape(host)}/">{html.escape(label)}'
            f"<small>{html.escape(blurb)}</small></a></li>"
        )
    nodes_html = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{html.escape(r)}</td>"
        f'<td class="{"ok" if ready == "True" else "bad"}">{html.escape(ready)}</td>'
        f"<td>{html.escape(v)}</td><td>{cpu}</td><td>{mem}</td></tr>"
        for n, r, ready, v, cpu, mem in d["nodes"]
    )
    by_ip = {}
    for host, _, _, _, ip in d["routes"]:
        by_ip.setdefault(ip or "<gateway-ip>", []).append(host)
    hosts = "\n".join(f"{ip:<16} {' '.join(hs)}" for ip, hs in sorted(by_ip.items()))
    return PAGE.format(
        host=html.escape(os.environ.get("BASE_DOMAIN", "")),
        menu="".join(items),
        nodes=nodes_html,
        hosts=html.escape(hosts),
        me=html.escape(me),
    )


@app.route("/ca")
@app.route("/ca.crt")
def ca():
    pem = ca_pem()
    if not pem:
        response.status = 404
        return f"ClusterIssuer {ISSUER} has no CA secret\n"
    response.content_type = "application/x-pem-file"
    response.set_header("Content-Disposition", 'inline; filename="ca.crt"')
    return pem


@app.route("/healthz")
def healthz():
    return "ok\n"


@app.route("/favicon.ico")
def favicon():
    return static_file("favicon.ico", root=HERE)


@app.route("/aviary.png")
def logo():
    return static_file("aviary004.png", root=HERE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8086")), debug=True)
