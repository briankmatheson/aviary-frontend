"""Aviary landing page.

A menu of everything the shared Gateway serves, built from the cluster's
HTTPRoutes (so a new vhost in aviary-deploy's local.vhosts shows up here
without touching this app), plus the cluster CA for download and a node
table.

Env:
  CLUSTER_ISSUER  cert-manager ClusterIssuer that signs the Gateway's certs;
                  /ca.crt serves its root: an ACME issuer's caBundle, or a
                  CA issuer's secret (default ca-issuer)
  PORT            listen port (default 8086)
"""
import base64
import gzip
import hmac
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import yaml
from bottle import Bottle, HTTPError, redirect, request, response, static_file
from kubernetes import client, config

app = Bottle()
HERE = os.path.dirname(os.path.abspath(__file__))
ISSUER = os.environ.get("CLUSTER_ISSUER", "ca-issuer")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "")
# Download the CA as ca.<domain>.crt, not a generic ca.crt: a per-cluster name
# installs alongside other clusters' roots instead of colliding with them in the
# trust store (several roots share the CN "Internal CA Root CA").
CA_FILENAME = f"ca.{BASE_DOMAIN}.crt" if BASE_DOMAIN else "ca.crt"

# Per-node disk throughput/IOPS come from the cluster's Prometheus
# (kube-prometheus-stack node-exporter). Reached over its in-cluster http
# service, so no extra TLS trust is needed; unset or unreachable -> '-'.
PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    "http://kube-prometheus-stack-prometheus.aviary-grafana.svc.cluster.local:9090",
).rstrip("/")

# --- Authentication (optional): log in via the local gitea's OAuth2, with a
# shared-token bypass for automation. All inert unless the OAuth env is set, so
# the page still runs without it. Server-to-server calls to gitea use its
# in-cluster http service (GITEA_INTERNAL) so no extra TLS trust is needed. ---
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "")
OAUTH_ISSUER = os.environ.get("OAUTH_ISSUER", "").rstrip("/")      # browser-facing gitea
GITEA_INTERNAL = os.environ.get("GITEA_INTERNAL", "").rstrip("/")  # in-cluster gitea (http)
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")             # https://<base_domain>
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
BYPASS_TOKEN = os.environ.get("BYPASS_TOKEN", "")
ADMIN_ONLY = os.environ.get("OAUTH_ADMIN_ONLY", "false").lower() in ("1", "true", "yes")
AUTH_ENABLED = bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET and OAUTH_ISSUER and SESSION_SECRET and BASE_URL)
REDIRECT_URI = f"{BASE_URL}/oauth/callback"
_GITEA_API = GITEA_INTERNAL or OAUTH_ISSUER
_PUBLIC_PATHS = {"/healthz", "/ca", "/ca.crt", "/favicon.ico", "/aviary.png",
                 "/login", "/logout", "/oauth/callback", f"/{CA_FILENAME}"}

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
    io = node_disk_io()
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
        bps, iops = io.get(n.metadata.name, (None, None))
        tput = f"{_hbytes(bps)}/s" if bps is not None else "-"
        iops_s = _hiops(iops) if iops is not None else "-"
        rows.append((
            n.metadata.name, roles, ready, n.status.node_info.kubelet_version,
            cpu, mem, tput, iops_s,
        ))
    return rows


_SUFFIX = {"n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "K": 1e3, "M": 1e6, "G": 1e9}


def _q(s):
    m = re.fullmatch(r"([0-9.]+)([a-zA-Z]*)", str(s))
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1)


def _hbytes(n):
    for u in ("B", "Ki", "Mi", "Gi", "Ti"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.0f}Pi"


def _hcpu(cores):
    return f"{cores * 1000:.0f}m" if cores < 1 else f"{cores:.1f}"


def _hiops(x):
    if x < 10:
        return f"{x:.1f}"
    if x < 1000:
        return f"{x:.0f}"
    return f"{x / 1000:.1f}k"


def metrics():
    """Rough per-namespace rollup: summed pod CPU/memory (metrics-server) and
    total PVC capacity. Apps live one-per-namespace, so keying by namespace is
    a good-enough stand-in until something reports per-app figures.

    Disk latency/throughput have no source yet (ABE would have to export
    per-volume IO stats), so they are left out here and shown as '-'.
    """
    cm = client.CustomObjectsApi()
    v1 = client.CoreV1Api()
    cpu, mem, disk = {}, {}, {}
    try:
        for p in cm.list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "pods"
        ).get("items", []):
            ns = p["metadata"]["namespace"]
            for c in p.get("containers", []):
                cpu[ns] = cpu.get(ns, 0) + _q(c["usage"]["cpu"])
                mem[ns] = mem.get(ns, 0) + _q(c["usage"]["memory"])
    except Exception:
        pass  # metrics-server optional
    try:
        for pvc in v1.list_persistent_volume_claim_for_all_namespaces().items:
            cap = (pvc.status.capacity or {}).get("storage")
            if cap:
                ns = pvc.metadata.namespace
                disk[ns] = disk.get(ns, 0) + _q(cap)
    except Exception:
        pass
    return {"cpu": cpu, "mem": mem, "disk": disk}


def _prom(expr):
    """{nodename: float} for a Prometheus instant query, keyed by the series'
    nodename label. {} on any error so the caller degrades to '-'."""
    url = f"{PROMETHEUS_URL}/api/v1/query?query=" + urllib.parse.quote(expr)
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode())
        return {
            s["metric"].get("nodename", ""): float(s["value"][1])
            for s in data.get("data", {}).get("result", [])
        }
    except Exception:
        return {}


def node_disk_io():
    """{nodename: (bytes_per_s, iops)} from node-exporter via Prometheus.

    The exporter labels series by `instance` (<nodeIP>:9100); node_uname_info
    carries both that and `nodename`, so a group_left join relabels to the node.
    Device-mapper (dm-*) devices are excluded so LVM volumes aren't counted on
    top of the physical disks they sit on. Empty if Prometheus is unset or
    unreachable, and the node table then shows '-'.
    """
    if not PROMETHEUS_URL:
        return {}
    dev = 'device!~"dm-.*"'
    tput = _prom(
        f"sum by (nodename) ((rate(node_disk_read_bytes_total{{{dev}}}[5m])"
        f"+rate(node_disk_written_bytes_total{{{dev}}}[5m]))"
        f" * on(instance) group_left(nodename) node_uname_info)"
    )
    iops = _prom(
        f"sum by (nodename) ((rate(node_disk_reads_completed_total{{{dev}}}[5m])"
        f"+rate(node_disk_writes_completed_total{{{dev}}}[5m]))"
        f" * on(instance) group_left(nodename) node_uname_info)"
    )
    out = {}
    for name in (set(tput) | set(iops)) - {""}:
        out[name] = (tput.get(name), iops.get(name))
    return out


# ---------------------------------------------------------------------------
# Helm: the Apps list can stop (helm uninstall) and start (reinstall) a release.
# Uninstall keeps the release history (--keep-history) and pins the app's PVCs
# with helm.sh/resource-policy=keep, so the data volumes survive; reinstall
# rebuilds the chart straight out of the kept release secret and re-adopts those
# volumes. The pod's ServiceAccount needs cluster-wide rights for this (see
# aviary-deploy/apps/aviary-frontend.tf).
# ---------------------------------------------------------------------------

# Helm runs as the pod's ServiceAccount (in-cluster); caches go under /tmp,
# which is writable for the 'nobody' user the image runs as.
_HELM_ENV = {
    **os.environ,
    "HELM_CACHE_HOME": "/tmp/helm/cache",
    "HELM_CONFIG_HOME": "/tmp/helm/config",
    "HELM_DATA_HOME": "/tmp/helm/data",
}


def _helm(*args, timeout=300):
    return subprocess.run(
        ["helm", *args], capture_output=True, text=True, env=_HELM_ENV, timeout=timeout
    )


def releases():
    """{(namespace, name): status} for every Helm release, uninstalled ones
    (kept history) included, so the menu can tell stopped apps from running."""
    out = {}
    try:
        r = _helm("list", "-A", "-a", "-o", "json", timeout=30)
        if r.returncode == 0:
            for rel in json.loads(r.stdout or "[]"):
                out[(rel["namespace"], rel["name"])] = rel["status"]
    except Exception:
        pass  # no helm, or not allowed: just no buttons
    return out


def _release_for(ns, label, rels):
    """The release backing an app in ns: its label if that is a release, else
    the sole release in the namespace, else None (ambiguous -> no button)."""
    if (ns, label) in rels:
        return label
    here = [name for (n, name) in rels if n == ns]
    if label in here:
        return label
    return here[0] if len(here) == 1 else None


def _release_obj(ns, rel):
    """The decoded latest Helm release object (embeds the chart + user values).

    A Helm 3 release secret stores base64(gzip(json)); Kubernetes returns that
    base64-encoded again, so .data['release'] is doubly base64-ed."""
    v1 = client.CoreV1Api()
    secs = v1.list_namespaced_secret(ns, label_selector=f"owner=helm,name={rel}").items
    if not secs:
        return None
    s = max(secs, key=lambda x: int(x.metadata.labels.get("version", "0")))
    blob = gzip.decompress(base64.b64decode(base64.b64decode(s.data["release"])))
    return json.loads(blob)


def _write_chart(chart, parent):
    """Reconstruct a chart directory (recursively, with subcharts) from the
    'chart' of a decoded release, and return its path."""
    meta = chart["metadata"]
    cdir = os.path.join(parent, meta["name"])
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "Chart.yaml"), "w") as f:
        yaml.safe_dump(meta, f)
    if chart.get("values") is not None:
        with open(os.path.join(cdir, "values.yaml"), "w") as f:
            yaml.safe_dump(chart["values"], f)
    if chart.get("schema"):
        with open(os.path.join(cdir, "values.schema.json"), "wb") as f:
            f.write(base64.b64decode(chart["schema"]))
    for group in ("templates", "files"):
        for t in chart.get(group) or []:
            p = os.path.join(cdir, t["name"])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(base64.b64decode(t["data"]))
    for dep in chart.get("dependencies") or []:
        _write_chart(dep, os.path.join(cdir, "charts"))
    return cdir


def _keep_pvcs(ns, rel):
    """Pin an app's PVCs so helm uninstall leaves the data behind. Prefer the
    release's own PVCs; fall back to every PVC in the namespace (apps here run
    one per namespace)."""
    v1 = client.CoreV1Api()
    pvcs = v1.list_namespaced_persistent_volume_claim(
        ns, label_selector=f"app.kubernetes.io/instance={rel}"
    ).items
    if not pvcs:
        pvcs = v1.list_namespaced_persistent_volume_claim(ns).items
    body = {"metadata": {"annotations": {"helm.sh/resource-policy": "keep"}}}
    for p in pvcs:
        try:
            v1.patch_namespaced_persistent_volume_claim(p.metadata.name, ns, body)
        except Exception:
            pass


def _purge_history(ns, rel):
    """Drop the kept release secrets so a fresh install can reuse the name."""
    v1 = client.CoreV1Api()
    for s in v1.list_namespaced_secret(ns, label_selector=f"owner=helm,name={rel}").items:
        try:
            v1.delete_namespaced_secret(s.metadata.name, ns)
        except Exception:
            pass


def _bump():
    with _lock:
        _cache["at"] = 0.0


def _fortune():
    """A fresh short fortune for the banner, run on every page load (not
    cached). /usr/games is not on nobody's PATH, so call it by full path."""
    try:
        r = subprocess.run(
            ["/usr/games/fortune", "-s"], capture_output=True, text=True, timeout=5
        )
        return r.stdout.rstrip() if r.returncode == 0 else ""
    except Exception:
        return ""


def ca_pem():
    """The root to trust for everything the Gateway serves.

    ACME issuer (the platform CA, e.g. step-ca on the management cluster):
    its caBundle is that root. CA issuer: the ca.crt in its secret.
    """
    cm = client.CustomObjectsApi()
    spec = cm.get_cluster_custom_object("cert-manager.io", "v1", "clusterissuers", ISSUER)["spec"]
    if spec.get("acme", {}).get("caBundle"):
        return base64.b64decode(spec["acme"]["caBundle"]).decode()
    name = spec.get("ca", {}).get("secretName")
    if not name:
        return None
    sec = client.CoreV1Api().read_namespaced_secret(name, "cert-manager")
    data = sec.data.get("ca.crt") or sec.data.get("tls.crt")
    return base64.b64decode(data).decode() if data else None


def snapshot():
    with _lock:
        if time.time() - _cache["at"] > 15:
            _cache["data"] = {
                "routes": routes(),
                "nodes": nodes(),
                "metrics": metrics(),
                "releases": releases(),
            }
            _cache["at"] = time.time()
        return _cache["data"]


def _node_rows_html(rows):
    """The <tbody> for the node table; also served on its own at /api/nodes so
    the page can refresh it in place without a full reload."""
    return "".join(
        f"<tr><td>{html.escape(n)}</td><td>{html.escape(r)}</td>"
        f'<td class="{"ok" if ready == "True" else "bad"}">{html.escape(ready)}</td>'
        f"<td>{html.escape(v)}</td><td>{cpu}</td><td>{mem}</td>"
        f"<td>{html.escape(tput)}</td><td>{html.escape(iops)}</td></tr>"
        for n, r, ready, v, cpu, mem, tput, iops in rows
    )


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
 .hdr {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }}
 .corner {{ text-align: right; font-size: 14px; flex: 0 0 auto; }}
 .corner .host {{ color: #555; font-weight: 600; }}
 .corner .acct {{ margin-top: 3px; }}
 .corner .acct .who {{ color: #999; margin-right: 8px; }}
 .corner .acct a {{ color: #1a4d8f; text-decoration: none; }}
 .corner .acct a:hover {{ text-decoration: underline; }}
 h1 {{ font-size: 56px; margin: 0 0 4px; letter-spacing: -1px; }}
 h1 small {{ font-size: 16px; color: #666; margin-left: 12px; letter-spacing: 0; }}
 h2 {{ margin: 36px 0 8px; font-size: 18px; color: #555; text-transform: uppercase; letter-spacing: 1px; }}
 ul.menu {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }}
 ul.menu li {{ display: flex; align-items: center; gap: 18px; padding: 12px 16px; background: rgba(255,255,255,.85);
               border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.08); transition: background .1s; }}
 ul.menu li:hover {{ background: #fffbe6; }}
 ul.menu li.off {{ opacity: .55; filter: grayscale(1); }}
 ul.menu li .app {{ flex: 1 1 auto; min-width: 0; }}
 ul.menu li .app a {{ text-decoration: none; color: #1a4d8f; font-size: 20px; }}
 ul.menu li.off .app a {{ color: #888; }}
 ul.menu li .app small {{ display: block; font-size: 13px; color: #666; }}
 ul.menu li .stats {{ display: flex; gap: 12px; flex: 0 0 auto; }}
 ul.menu li .stat {{ text-align: right; min-width: 62px; }}
 ul.menu li .stat b {{ display: block; font-size: 15px; color: #333; font-weight: 600; font-variant-numeric: tabular-nums; }}
 ul.menu li .stat span {{ font-size: 10px; color: #999; text-transform: uppercase; letter-spacing: .5px; }}
 ul.menu li .act {{ flex: 0 0 auto; margin: 0; width: 34px; text-align: center; }}
 ul.menu li .act button {{ cursor: pointer; border: 1px solid #d8dde5; border-radius: 6px; background: #fff;
                           width: 30px; height: 30px; font-size: 14px; line-height: 1; color: #777; }}
 ul.menu li .act.stop button:hover {{ background: #ffecec; border-color: #e0a0a0; color: #b00020; }}
 ul.menu li .act.start button:hover {{ background: #e8f5e9; border-color: #a0cfa5; color: #1b7f3b; }}
 table {{ border-collapse: collapse; background: rgba(255,255,255,.85); width: 100%; font-size: 14px; }}
 th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #e3e3df; }}
 th {{ color: #666; font-weight: 600; }}
 pre {{ background: rgba(255,255,255,.85); padding: 12px; overflow-x: auto; font-size: 13px; }}
 pre.fortune {{ border-left: 3px solid #4682b4; padding: 10px 14px; margin: 8px 0 0;
                font-size: 13px; color: #555; font-style: italic; white-space: pre-wrap; }}
 .ok {{ color: #1b7f3b; }} .bad {{ color: #b00020; }}
 footer {{ margin-top: 48px; color: #888; font-size: 13px; }}
</style></head><body><main>
<div class="hdr">
<nav><a href="/{ca_name}" download="{ca_name}" title="Cluster CA: trust this to stop the browser warnings">{ca_name}</a></nav>
<div class="corner"><div class="host">{host}</div>{auth_nav}</div>
</div>
<h1>Aviary</h1>
{fortune}
<h2>Apps</h2>
<ul class="menu">{menu}</ul>
<h2>Cluster</h2>
<table id="nodes"><thead><tr><th>Node</th><th>Role</th><th>Ready</th><th>Kubelet</th><th>CPU</th><th>Memory</th><th>Disk tput</th><th>IOPS</th></tr></thead><tbody id="noderows">{nodes}</tbody></table>
<h2>/etc/hosts</h2>
<p>If your resolver does not know these names:</p>
<pre>{hosts}</pre>
<footer>Served by {me}</footer>
</main>
<script>
// Keep the node table live without reloading the page: pull the <tbody> from
// /api/nodes every 10s (carrying the session cookie) and swap it in. Silent on
// error so a transient blip just leaves the last-good rows on screen.
// (Braces are doubled because this page is rendered with str.format().)
(function () {{
  var tb = document.getElementById('noderows');
  if (!tb) return;
  function refresh() {{
    fetch('/api/nodes', {{ credentials: 'same-origin' }})
      .then(function (r) {{ return r.ok ? r.text() : Promise.reject(r.status); }})
      .then(function (h) {{ tb.innerHTML = h; }})
      .catch(function () {{}});
  }}
  setInterval(refresh, 10000);
}})();
</script>
</body></html>
"""


def _http_post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _http_get_json(url, bearer):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _bypass_ok():
    if not BYPASS_TOKEN:
        return False
    auth = request.get_header("Authorization", "") or ""
    tok = auth[7:] if auth.startswith("Bearer ") else ""
    tok = tok or request.get_header("X-Aviary-Token", "") or request.query.get("token", "")
    return bool(tok) and hmac.compare_digest(tok, BYPASS_TOKEN)


def _session_user():
    try:
        return request.get_cookie("aviary_session", secret=SESSION_SECRET)
    except Exception:
        return None


@app.hook("before_request")
def _auth_gate():
    if not AUTH_ENABLED or request.path in _PUBLIC_PATHS:
        return
    if _bypass_ok() or _session_user():
        return
    if request.method == "GET":
        redirect("/login")
    raise HTTPError(401, "authentication required\n")


@app.route("/login")
def login():
    if not AUTH_ENABLED:
        redirect("/")
    state = secrets.token_urlsafe(16)
    response.set_cookie("oauth_state", state, secret=SESSION_SECRET, httponly=True,
                        secure=True, samesite="lax", max_age=600, path="/")
    q = urllib.parse.urlencode({
        "client_id": OAUTH_CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "state": state,
    })
    redirect(f"{OAUTH_ISSUER}/login/oauth/authorize?{q}")


@app.route("/oauth/callback")
def oauth_callback():
    if not AUTH_ENABLED:
        redirect("/")
    saved = request.get_cookie("oauth_state", secret=SESSION_SECRET)
    if not saved or request.query.get("state") != saved:
        raise HTTPError(400, "bad OAuth state")
    code = request.query.get("code", "")
    if not code:
        raise HTTPError(400, "no authorization code")
    tok = _http_post_form(f"{_GITEA_API}/login/oauth/access_token", {
        "grant_type": "authorization_code", "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET, "code": code, "redirect_uri": REDIRECT_URI,
    })
    access = tok.get("access_token")
    if not access:
        raise HTTPError(502, "token exchange failed")
    user = _http_get_json(f"{_GITEA_API}/api/v1/user", access)
    username = user.get("login") or user.get("username") or "?"
    if ADMIN_ONLY and not user.get("is_admin"):
        raise HTTPError(403, f"{username} is not an admin")
    response.delete_cookie("oauth_state", path="/")
    response.set_cookie("aviary_session", username, secret=SESSION_SECRET, httponly=True,
                        secure=True, samesite="lax", max_age=43200, path="/")
    redirect("/")


@app.route("/logout")
def logout():
    response.delete_cookie("aviary_session", path="/", secure=True, samesite="lax")
    # Don't bounce to /login: gitea's SSO session is still live, so it would
    # silently re-authenticate and the logout would look like it did nothing.
    return (
        "<!doctype html><meta charset=utf-8><title>Aviary</title>"
        '<body style="font:16px/1.5 system-ui,sans-serif;text-align:center;'
        'padding:64px;color:#333">Logged out. '
        '<a href="/login">Log in again</a></body>'
    )


@app.route("/")
def index():
    d = snapshot()
    me = os.environ.get("HOSTNAME", "")
    items = []
    m = d["metrics"]
    rels = d["releases"]
    for host, ns, svc, port, ip in d["routes"]:
        if svc == "aviary-frontend":
            continue  # that's us
        label = host.split(".", 1)[0]
        blurb = BLURBS.get(label, f"{ns}/{svc}:{port}")
        mem = _hbytes(m["mem"][ns]) if ns in m["mem"] else "-"
        cpu = _hcpu(m["cpu"][ns]) if ns in m["cpu"] else "-"
        disk = _hbytes(m["disk"][ns]) if ns in m["disk"] else "-"
        rel = _release_for(ns, label, rels)
        off = bool(rel) and rels.get((ns, rel)) == "uninstalled"
        if not rel:
            act = '<div class="act"></div>'  # not a helm release: no button
        else:
            verb, cls, icon, tip = (
                ("install", "start", "&#9654;", "reinstall (re-attaches the same volumes)")
                if off
                else ("uninstall", "stop", "&#9632;", "helm uninstall (keeps volumes)")
            )
            act = (
                f'<form class="act {cls}" method="post" '
                f'action="/app/{html.escape(ns)}/{html.escape(rel)}/{verb}">'
                f'<button title="{tip}">{icon}</button></form>'
            )
        items.append(
            f'<li class="{"off" if off else ""}"><div class="app">'
            f'<a href="https://{html.escape(host)}/">{html.escape(label)}</a>'
            f"<small>{html.escape(blurb)}</small></div>"
            f'<div class="stats">'
            f'<div class="stat"><b>{mem}</b><span>mem</span></div>'
            f'<div class="stat"><b>{cpu}</b><span>cpu</span></div>'
            f'<div class="stat"><b>{disk}</b><span>disk</span></div>'
            f'<div class="stat"><b>&mdash;</b><span>lat</span></div>'
            f'<div class="stat"><b>&mdash;</b><span>tput</span></div>'
            f"</div>{act}</li>"
        )
    nodes_html = _node_rows_html(d["nodes"])
    by_ip = {}
    for host, _, _, _, ip in d["routes"]:
        by_ip.setdefault(ip or "<gateway-ip>", []).append(host)
    hosts = "\n".join(f"{ip:<16} {' '.join(hs)}" for ip, hs in sorted(by_ip.items()))
    fort = _fortune()
    fort_html = f'<pre class="fortune">{html.escape(fort)}</pre>' if fort else ""
    if AUTH_ENABLED:
        u = _session_user()
        auth_nav = (
            f'<div class="acct"><span class="who">{html.escape(u)}</span>'
            f'<a href="/logout">log out</a></div>'
            if u else '<div class="acct"><a href="/login">log in</a></div>'
        )
    else:
        auth_nav = ""
    return PAGE.format(
        host=html.escape(os.environ.get("BASE_DOMAIN", "")),
        ca_name=html.escape(CA_FILENAME),
        auth_nav=auth_nav,
        fortune=fort_html,
        menu="".join(items),
        nodes=nodes_html,
        hosts=html.escape(hosts),
        me=html.escape(me),
    )


@app.route("/api/nodes")
def api_nodes():
    """The node table body, for the page's live refresh. Gated like the rest of
    the app (not a public path), so the browser's session cookie carries in."""
    response.content_type = "text/html; charset=utf-8"
    return _node_rows_html(snapshot()["nodes"])


@app.route("/app/<ns>/<rel>/uninstall", method="POST")
def app_stop(ns, rel):
    """Stop an app: pin its PVCs so the data survives, then helm uninstall
    keeping the release history (the chart to reinstall from lives in it)."""
    _keep_pvcs(ns, rel)
    r = _helm("uninstall", rel, "-n", ns, "--keep-history", timeout=300)
    _bump()
    if r.returncode != 0:
        response.status = 500
        return f"helm uninstall {rel} failed:\n{r.stderr}"
    redirect("/")


@app.route("/app/<ns>/<rel>/install", method="POST")
def app_start(ns, rel):
    """Start a stopped app: rebuild the chart from the kept release secret and
    install it again, re-adopting the volumes left behind."""
    obj = _release_obj(ns, rel)
    if not obj:
        response.status = 404
        return f"no saved release for {rel} in {ns}\n"
    work = tempfile.mkdtemp(prefix="chart-", dir="/tmp")
    try:
        cdir = _write_chart(obj["chart"], work)
        vals = os.path.join(work, "values.yaml")
        with open(vals, "w") as f:
            yaml.safe_dump(obj.get("config") or {}, f)
        _purge_history(ns, rel)
        r = _helm("install", rel, cdir, "-n", ns, "-f", vals, "--wait=false", timeout=600)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    _bump()
    if r.returncode != 0:
        response.status = 500
        return f"helm install {rel} failed:\n{r.stderr}"
    redirect("/")


@app.route("/ca")
@app.route("/ca.crt")
def ca():
    pem = ca_pem()
    if not pem:
        response.status = 404
        return f"ClusterIssuer {ISSUER} has no CA secret\n"
    response.content_type = "application/x-pem-file"
    response.set_header("Content-Disposition", f'inline; filename="{CA_FILENAME}"')
    return pem


# Also serve it at /ca.<domain>.crt so the URL basename is the per-cluster name.
if CA_FILENAME != "ca.crt":
    app.route(f"/{CA_FILENAME}")(ca)


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
