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
import math
import os
import re
import secrets
import shutil
import ssl
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

# Platform plumbing rather than things people open to do work, listed under
# their own heading below the apps. aviary-deploy says which is which with an
# aviary/group label ("apps" or "system") on each HTTPRoute; this list is only
# the fallback for a route without one. Keyed like BLURBS; unlisted means app.
GROUP_LABEL = "aviary/group"
SYSTEM = {"grafana", "headlamp", "velero", "postgres-ui", "minio"}

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()

# A separate, short-lived cache for just the node table. The page polls
# /api/nodes several times a second (far more often than the 15s page
# snapshot), so this bounds how hard that hits the API without letting the
# table feel stale.
_ncache = {"at": 0.0, "data": None}
_nlock = threading.Lock()


def routes():
    """[(host, namespace, service, port, gateway_ip, group)] for every
    HTTPRoute; group is its aviary/group label ("" if unlabelled)."""
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
        group = (r["metadata"].get("labels") or {}).get(GROUP_LABEL, "")
        ip = ""
        for p in spec.get("parentRefs", []):
            ip = gws.get((p.get("namespace", ns), p.get("name")), "") or ip
        for rule in spec.get("rules", []):
            # The https-redirect route has filters and no backends; skip it.
            for b in rule.get("backendRefs", []):
                for h in hosts:
                    out.append((h, b.get("namespace", ns), b.get("name", ""), b.get("port", ""), ip, group))
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
    peak_bps, peak_iops = node_disk_peak(io)
    rootfs = node_root_fs()
    rows = []
    for n in v1.list_node().items:
        ready = next((c.status for c in n.status.conditions if c.type == "Ready"), "Unknown")
        roles = ",".join(
            k.split("/", 1)[1] for k in n.metadata.labels if k.startswith("node-role.kubernetes.io/")
        ) or "worker"
        u = usage.get(n.metadata.name)
        cpu = mem = "-"
        fcpu = fmem = None
        if u:
            cpu = "%d%%" % (100 * _q(u["cpu"]) / _q(n.status.allocatable["cpu"]))
            mem = "%d%%" % (100 * _q(u["memory"]) / _q(n.status.allocatable["memory"]))
            # Heat is against the node's real capacity, not allocatable.
            fcpu = _frac(_q(u["cpu"]), _q(n.status.capacity["cpu"]))
            fmem = _frac(_q(u["memory"]), _q(n.status.capacity["memory"]))
        bps, iops = io.get(n.metadata.name, (None, None))
        tput = f"{_hbytes(bps)}/s" if bps is not None else "-"
        iops_s = _hiops(iops) if iops is not None else "-"
        used, size = rootfs.get(n.metadata.name, (None, None))
        dcap = f"{_hbytes(used)} / {_hbytes(size)}" if used is not None and size else "-"
        rows.append((
            n.metadata.name, roles, ready, n.status.node_info.kubelet_version,
            cpu, mem, dcap, tput, iops_s,
            fcpu, fmem, _frac(used, size), _logfrac(bps, peak_bps), _logfrac(iops, peak_iops),
        ))
    return rows


_SUFFIX = {"n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "K": 1e3, "M": 1e6, "G": 1e9}


def _q(s):
    m = re.fullmatch(r"([0-9.]+)([a-zA-Z]*)", str(s))
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1)


def _frac(value, top):
    """value/top clamped to 0..1, or None when there is no scale to judge by."""
    if value is None or not top or top <= 0:
        return None
    return min(1.0, max(0.0, value / top))


# Disk rates span orders of magnitude (an idle node does a few KiB/s, a busy one
# hundreds of MiB/s), so on a linear scale everything but the peak would read as
# "min". Spread the bottom three decades below the peak across the spectrum.
_DISK_DECADES = 3


def _logfrac(value, top):
    if value is None or not top or top <= 0:
        return None
    if value <= 0:
        return 0.0
    return min(1.0, max(0.0, 1 + math.log10(value / top) / _DISK_DECADES))


def _heat(frac, title=""):
    """Inline attributes colouring a value by where it sits between min and max:
    a continuous sweep of the spectrum, blue (0) through green (0.5) to red (1).
    Empty when there is no scale (frac is None), leaving the default colour."""
    if frac is None:
        return ""
    t = f' title="{html.escape(title)}"' if title else ""
    return f' class="heat" style="color:hsl({240 * (1 - frac):.0f},90%,38%)"{t}'


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
    cpu_max, mem_max, unset = app_limits()
    tuned = set()
    try:
        tuned = {
            lr.metadata.namespace
            for lr in v1.list_limit_range_for_all_namespaces().items
            if lr.metadata.name == LIMITRANGE
        }
    except Exception:
        pass
    return {"cpu": cpu, "mem": mem, "disk": disk,
            "cpu_max": cpu_max, "mem_max": mem_max, "unset": unset, "tuned": tuned}


# ---------------------------------------------------------------------------
# Images: the image menu can retag a workload, but only for images that live in
# the mesh registry (our own builds) -- that is the one registry we can list
# and date tags for. Credentials come from the pull secret already in this
# namespace; its cert is signed by the internal CA, trusted via the
# trust-manager bundle ConfigMap (read over the API, so no extra mount).
# ---------------------------------------------------------------------------
IMAGE_REGISTRY = os.environ.get("IMAGE_REGISTRY", "registry.mesh.bmath.nyc")
IMAGE_PULL_SECRET = os.environ.get("IMAGE_PULL_SECRET", "mesh-reg")
CA_BUNDLE_CONFIGMAP = os.environ.get("CA_BUNDLE_CONFIGMAP", "xdebbie-ca-bundle")
_MANIFEST_TYPES = ", ".join((
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
))
_rcache = {"at": 0.0, "auth": None, "ctx": None}
_tcache = {}
_rlock = threading.Lock()


def self_namespace():
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
            return f.read().strip()
    except OSError:
        return os.environ.get("POD_NAMESPACE", "aviary")


def _registry_access():
    """(Authorization header, ssl context) for the mesh registry, cached 5 min."""
    with _rlock:
        if time.time() - _rcache["at"] > 300:
            v1 = client.CoreV1Api()
            ns = self_namespace()
            sec = v1.read_namespaced_secret(IMAGE_PULL_SECRET, ns)
            auths = json.loads(base64.b64decode(sec.data[".dockerconfigjson"]))["auths"]
            a = auths[IMAGE_REGISTRY]
            token = a.get("auth") or base64.b64encode(
                f"{a['username']}:{a['password']}".encode()).decode()
            ctx = ssl.create_default_context()
            try:
                cm = v1.read_namespaced_config_map(CA_BUNDLE_CONFIGMAP, ns)
                ctx.load_verify_locations(cadata="".join((cm.data or {}).values()))
            except Exception:
                pass  # no bundle: system roots only
            _rcache.update(at=time.time(), auth=f"Basic {token}", ctx=ctx)
        return _rcache["auth"], _rcache["ctx"]


def _registry_json(path, accept=None):
    auth, ctx = _registry_access()
    headers = {"Authorization": auth}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(f"https://{IMAGE_REGISTRY}/v2/{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read().decode())


def _tag_created(repo, tag):
    """When the image behind a tag was built (its config's `created`), or ""."""
    try:
        m = _registry_json(f"{repo}/manifests/{tag}", _MANIFEST_TYPES)
        if "manifests" in m:  # multi-arch index: date its first image
            m = _registry_json(f"{repo}/manifests/{m['manifests'][0]['digest']}", _MANIFEST_TYPES)
        return _registry_json(f"{repo}/blobs/{m['config']['digest']}").get("created", "")
    except Exception:
        return ""


def image_tags(repo):
    """Tags to offer for a mesh-registry repository: `latest` first (if it
    exists), then the five most recently built others. Cached for a minute."""
    hit = _tcache.get(repo)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    tags = _registry_json(f"{repo}/tags/list").get("tags") or []
    dated = sorted(((_tag_created(repo, t), t) for t in tags if t != "latest"), reverse=True)
    out = (["latest"] if "latest" in tags else []) + [t for _, t in dated[:5]]
    _tcache[repo] = (time.time(), out)
    return out


def _mesh_image(image):
    """(repo, tag) if image is a tagged mesh-registry image, else None."""
    prefix = IMAGE_REGISTRY + "/"
    if not image.startswith(prefix) or "@" in image:
        return None
    repo, _, tag = image[len(prefix):].rpartition(":")
    return (repo, tag) if repo else (tag, "latest")


_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")


def _workload_api(kind):
    apps = client.AppsV1Api()
    return {
        "Deployment": (apps.list_namespaced_deployment, apps.read_namespaced_deployment,
                       apps.patch_namespaced_deployment),
        "StatefulSet": (apps.list_namespaced_stateful_set, apps.read_namespaced_stateful_set,
                        apps.patch_namespaced_stateful_set),
        "DaemonSet": (apps.list_namespaced_daemon_set, apps.read_namespaced_daemon_set,
                      apps.patch_namespaced_daemon_set),
    }[kind]


def app_images(ns):
    """Every workload in ns with its containers' images, for the image menu.
    A container on a mesh-registry image also carries the tags it may be set to
    (`tags`); the rest are listed read-only (`tags` is None)."""
    out = []
    for kind in _WORKLOAD_KINDS:
        for w in _workload_api(kind)[0](ns).items:
            containers = []
            for c in w.spec.template.spec.containers:
                mesh = _mesh_image(c.image)
                tags = tag = None
                if mesh:
                    tag = mesh[1]
                    try:
                        tags = image_tags(mesh[0])
                    except Exception:
                        tags = []  # registry unreachable: show, but nothing to pick
                    if tag not in tags:
                        tags = tags + [tag]  # keep the running tag selectable
                containers.append({"name": c.name, "image": c.image, "tag": tag, "tags": tags})
            out.append({"kind": kind, "name": w.metadata.name, "containers": containers})
    return out


def image_namespaces():
    """Where the image menu works: the apps, plus this page's own namespace."""
    return app_namespaces() | {self_namespace()}


# The per-namespace LimitRange the requests/limits popup writes: default request
# and limit for every container in the app that does not set its own.
LIMITRANGE = "aviary-defaults"


def _limit_range(ns):
    """(request, limit) dicts of quantities from the app's LimitRange, or
    ({}, {}) if it has none."""
    try:
        lr = client.CoreV1Api().read_namespaced_limit_range(LIMITRANGE, ns)
    except Exception:
        return {}, {}
    for item in lr.spec.limits or []:
        if item.type == "Container":
            return item.default_request or {}, item.default or {}
    return {}, {}


def app_resources(ns):
    """What the requests/limits popup needs for one app, per resource, in
    millicores (cpu) and Mi (memory):

      usage      the app's busiest container right now (the values are per
                 container, so that is the one a limit has to clear)
      top        the scale's maximum: the largest node, since no container can
                 be given more
      floor      the lowest limit that keeps every pod admissible: a container
                 that sets a request but no limit is rejected if the default
                 limit is below its request
      request,
      limit      the LimitRange's current values, or a suggestion if unset
      saved      whether those came from an existing LimitRange
    """
    v1 = client.CoreV1Api()
    unit = {"cpu": 1e-3, "memory": 2**20}
    usage = {"cpu": 0.0, "memory": 0.0}
    try:
        for p in client.CustomObjectsApi().list_namespaced_custom_object(
            "metrics.k8s.io", "v1beta1", ns, "pods"
        ).get("items", []):
            for c in p.get("containers", []):
                for res in usage:
                    usage[res] = max(usage[res], _q(c["usage"][res]))
    except Exception:
        pass  # metrics-server optional: the fill just stays empty
    top = {"cpu": 0.0, "memory": 0.0}
    for n in v1.list_node().items:
        for res in top:
            top[res] = max(top[res], _q(n.status.capacity[res]))
    floor = {"cpu": 0.0, "memory": 0.0}
    for p in v1.list_namespaced_pod(ns).items:
        for c in p.spec.containers + (p.spec.init_containers or []):
            req = (c.resources.requests if c.resources else None) or {}
            lim = (c.resources.limits if c.resources else None) or {}
            for res in floor:
                if res in req and res not in lim:
                    floor[res] = max(floor[res], _q(req[res]))
    req, lim = _limit_range(ns)
    least = {"cpu": 0.010, "memory": 32 * 2**20}  # smallest sensible suggestion
    out = {"saved": bool(req or lim)}
    for res, key in (("cpu", "cpu"), ("memory", "mem")):
        r = _q(req[res]) if res in req else max(usage[res] * 1.25, least[res])
        l = _q(lim[res]) if res in lim else max(2 * r, floor[res])
        l = min(l, top[res])
        out[key] = {
            "usage": usage[res] / unit[res],
            "top": top[res] / unit[res],
            "floor": floor[res] / unit[res],
            "request": min(r, l) / unit[res],
            "limit": l / unit[res],
        }
    return out


def app_namespaces():
    """Namespaces the menu lists (this page's own included): the only ones the
    controls may change."""
    return {ns for _, ns, _, _, _, _ in snapshot()["routes"]}


def restart_workloads(ns):
    """Roll every Deployment/StatefulSet/DaemonSet in ns (as kubectl rollout
    restart does), so pods are recreated and pick up the new defaults."""
    apps = client.AppsV1Api()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = {"spec": {"template": {"metadata": {"annotations": {
        "kubectl.kubernetes.io/restartedAt": stamp}}}}}
    for lister, patch in (
        (apps.list_namespaced_deployment, apps.patch_namespaced_deployment),
        (apps.list_namespaced_stateful_set, apps.patch_namespaced_stateful_set),
        (apps.list_namespaced_daemon_set, apps.patch_namespaced_daemon_set),
    ):
        for w in lister(ns).items:
            patch(w.metadata.name, ns, body)


def app_limits():
    """({ns: cores}, {ns: bytes}, {ns: {what: count}}): the most each
    namespace's running pods may use, and how many of its containers leave a
    request or limit unset (e.g. {"memory limit": 3}). The maximum is the sum of their containers' limits; a container without a
    limit is bounded only by the node it runs on, so it contributes that node's
    capacity (counted once per node per namespace, however many unlimited
    containers share it)."""
    v1 = client.CoreV1Api()
    cpu, mem, unset = {}, {}, {}
    try:
        cap = {
            n.metadata.name: (_q(n.status.capacity["cpu"]), _q(n.status.capacity["memory"]))
            for n in v1.list_node().items
        }
        open_cpu, open_mem = set(), set()  # (ns, node) with an unlimited container
        for p in v1.list_pod_for_all_namespaces(field_selector="status.phase=Running").items:
            ns, node = p.metadata.namespace, p.spec.node_name
            for c in p.spec.containers:
                lim = (c.resources.limits if c.resources else None) or {}
                req = (c.resources.requests if c.resources else None) or {}
                for kind, have in (("request", req), ("limit", lim)):
                    for res in ("cpu", "memory"):
                        # A limit with no request defaults the request to it.
                        if res not in have and not (kind == "request" and res in lim):
                            gaps = unset.setdefault(ns, {})
                            gaps[f"{res} {kind}"] = gaps.get(f"{res} {kind}", 0) + 1
                for res, total, unbounded, idx in (
                    ("cpu", cpu, open_cpu, 0), ("memory", mem, open_mem, 1)
                ):
                    if res in lim:
                        total[ns] = total.get(ns, 0) + _q(lim[res])
                    elif node in cap and (ns, node) not in unbounded:
                        unbounded.add((ns, node))
                        total[ns] = total.get(ns, 0) + cap[node][idx]
    except Exception:
        pass  # no limits known: the stats just stay uncoloured
    return cpu, mem, unset


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


def node_root_fs():
    """{nodename: (used_bytes, size_bytes)} for each node's own root filesystem
    (the local disk; ABE volumes are separate block devices and not counted)."""
    if not PROMETHEUS_URL:
        return {}
    join = " * on(instance) group_left(nodename) node_uname_info"
    size = _prom(f'max by (nodename) (node_filesystem_size_bytes{{mountpoint="/"}}{join})')
    avail = _prom(f'max by (nodename) (node_filesystem_avail_bytes{{mountpoint="/"}}{join})')
    return {n: (size[n] - avail[n], size[n]) for n in size if n and n in avail}


_pcache = {"at": 0.0, "data": (None, None)}
_plock = threading.Lock()


def node_disk_peak(io):
    """(bytes_per_s, iops): the top of the disk scales. Disks advertise no
    throughput capacity, so the ceiling is the busiest any node has actually
    been over the last 24h (and never less than what is on screen right now).
    The 24h subquery is cached for a minute; the peak moves slowly."""
    if not PROMETHEUS_URL:
        return None, None
    with _plock:
        if time.time() - _pcache["at"] > 60:
            dev = 'device!~"dm-.*"'
            join = " * on(instance) group_left(nodename) node_uname_info"
            tput = _prom(
                f"max_over_time((sum by (nodename) ((rate(node_disk_read_bytes_total{{{dev}}}[5m])"
                f"+rate(node_disk_written_bytes_total{{{dev}}}[5m])){join}))[24h:5m])"
            )
            iops = _prom(
                f"max_over_time((sum by (nodename) ((rate(node_disk_reads_completed_total{{{dev}}}[5m])"
                f"+rate(node_disk_writes_completed_total{{{dev}}}[5m])){join}))[24h:5m])"
            )
            _pcache["data"] = (max(tput.values(), default=None), max(iops.values(), default=None))
            _pcache["at"] = time.time()
        peak_bps, peak_iops = _pcache["data"]
    now_bps = [b for b, _ in io.values() if b is not None]
    now_iops = [i for _, i in io.values() if i is not None]
    return (
        max([peak_bps or 0, *now_bps]) or None,
        max([peak_iops or 0, *now_iops]) or None,
    )


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


def nodes_snapshot():
    """Node rows on a short (1s) cache, independent of the 15s page snapshot, so
    the live /api/nodes poll stays cheap however fast the browser asks (the
    underlying sources -- metrics-server, Prometheus rates -- only move every
    ~15-30s anyway, so 1s is already finer than the data changes)."""
    with _nlock:
        if time.time() - _ncache["at"] > 1:
            _ncache["data"] = nodes()
            _ncache["at"] = time.time()
        return _ncache["data"]


def _node_rows_html(rows):
    """The <tbody> for the node table; also served on its own at /api/nodes so
    the page can refresh it in place without a full reload."""
    return "".join(
        f"<tr><td>{html.escape(n)}</td><td>{html.escape(r)}</td>"
        f'<td class="{"ok" if ready == "True" else "bad"}">{html.escape(ready)}</td>'
        f"<td>{html.escape(v)}</td>"
        f"<td{_heat(fcpu)}>{cpu}</td><td{_heat(fmem)}>{mem}</td>"
        f"<td{_heat(fdcap)}>{html.escape(dcap)}</td>"
        f"<td{_heat(ftput)}>{html.escape(tput)}</td><td{_heat(fiops)}>{html.escape(iops)}</td></tr>"
        for n, r, ready, v, cpu, mem, dcap, tput, iops, fcpu, fmem, fdcap, ftput, fiops in rows
    )


RL_CSS = """
 ul.menu li .act .warn { display: inline-block; width: 22px; height: 22px; padding: 0;
   border: 0; border-radius: 50%; background: #d11a2a; color: #e5e5e5; font: 700 15px/22px system-ui, sans-serif;
   text-align: center; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,.25); }
 ul.menu li .act .warn:hover { background: #a80f1d; }
 ul.menu li .act .warn.set { background: #c9ced6; color: #555; font-size: 13px; }
 ul.menu li .act .warn.set:hover { background: #b3bac4; }
 dialog#rl { border: 0; border-radius: 10px; padding: 22px 26px; width: min(560px, 92vw);
   box-shadow: 0 12px 40px rgba(0,0,0,.3); font: 15px/1.4 system-ui, sans-serif; color: #222; }
 dialog#rl::backdrop { background: rgba(20,30,45,.45); }
 #rl h3 { margin: 0 0 4px; font-size: 20px; }
 #rl p.note { margin: 0 0 18px; font-size: 13px; color: #666; }
 #rl .rl-row { margin-bottom: 20px; }
 #rl .rl-head { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; color: #555; }
 #rl .rl-head b { font-size: 15px; color: #222; }
 #rl .rl-head .now { font-variant-numeric: tabular-nums; }
 #rl .rl-slider { position: relative; height: 34px; margin-top: 6px; }
 #rl .rl-track { position: absolute; left: 0; right: 0; top: 11px; height: 12px; border-radius: 6px;
   background: #e6e9ee; overflow: hidden; }
 #rl .rl-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; }
 #rl .rl-band { position: absolute; top: 9px; height: 16px; border: 2px solid #1a4d8f; border-radius: 8px;
   box-sizing: border-box; pointer-events: none; }
 #rl .rl-slider input[type=range] { position: absolute; left: 0; top: 0; width: 100%; height: 34px; margin: 0;
   background: none; pointer-events: none; -webkit-appearance: none; appearance: none; }
 #rl .rl-slider input[type=range]::-webkit-slider-runnable-track { background: none; height: 34px; }
 #rl .rl-slider input[type=range]::-moz-range-track { background: none; }
 #rl .rl-slider input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; pointer-events: auto;
   width: 20px; height: 20px; margin-top: 7px; border-radius: 50%; background: #fff; border: 3px solid #1a4d8f;
   cursor: grab; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
 #rl .rl-slider input[type=range]::-moz-range-thumb { pointer-events: auto; width: 14px; height: 14px;
   border-radius: 50%; background: #fff; border: 3px solid #1a4d8f; cursor: grab; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
 #rl .rl-vals { display: flex; justify-content: space-between; font-size: 13px; color: #555;
   font-variant-numeric: tabular-nums; margin-top: 2px; }
 #rl .rl-vals b { color: #1a4d8f; }
 #rl .rl-foot { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
 #rl .rl-foot label { flex: 1 1 auto; font-size: 14px; color: #444; }
 #rl .rl-foot button { cursor: pointer; padding: 7px 16px; border-radius: 6px; border: 1px solid #d8dde5;
   background: #fff; font-size: 14px; }
 #rl .rl-foot button.go { background: #1a4d8f; border-color: #1a4d8f; color: #fff; }
 #rl .rl-err { color: #b00020; font-size: 13px; min-height: 18px; margin-top: 8px; }
"""

RL_HTML = """
<dialog id="rl"><form method="post">
 <h3>Requests &amp; limits: <span id="rl-app"></span></h3>
 <p class="note">Defaults for each container in this app that sets none of its own
 (a namespace LimitRange). The bar is filled to the app's busiest container.</p>
 <div class="rl-row" data-res="cpu"><div class="rl-head"><b>CPU</b><span class="now"></span></div>
  <div class="rl-slider"><div class="rl-track"><div class="rl-fill"></div></div><div class="rl-band"></div>
   <input type="range" class="lo" min="0" max="1000" step="1" aria-label="CPU request">
   <input type="range" class="hi" min="0" max="1000" step="1" aria-label="CPU limit"></div>
  <div class="rl-vals"><span>request <b class="req"></b></span><span>limit <b class="lim"></b></span></div>
  <input type="hidden" name="cpu_request"><input type="hidden" name="cpu_limit"></div>
 <div class="rl-row" data-res="mem"><div class="rl-head"><b>Memory</b><span class="now"></span></div>
  <div class="rl-slider"><div class="rl-track"><div class="rl-fill"></div></div><div class="rl-band"></div>
   <input type="range" class="lo" min="0" max="1000" step="1" aria-label="Memory request">
   <input type="range" class="hi" min="0" max="1000" step="1" aria-label="Memory limit"></div>
  <div class="rl-vals"><span>request <b class="req"></b></span><span>limit <b class="lim"></b></span></div>
  <input type="hidden" name="mem_request"><input type="hidden" name="mem_limit"></div>
 <div class="rl-foot"><label><input type="checkbox" name="restart" value="1"> restart the app now to apply</label>
  <button type="button" class="cancel">Cancel</button><button class="go">Apply</button></div>
 <div class="rl-err"></div>
</form></dialog>
<script>
// Requests/limits popup. Each row is a two-thumb slider: left thumb = request,
// right thumb = limit, track filled to current usage. Values are millicores
// (cpu) and Mi (memory). Positions run 0..1000 on a cubic scale so the low end,
// where most containers live, gets most of the travel.
(function () {
  var dlg = document.getElementById('rl');
  if (!dlg || !dlg.showModal) return;
  var form = dlg.querySelector('form'), err = dlg.querySelector('.rl-err');
  function fmt(res, v) {
    if (res === 'cpu') return v < 1000 ? Math.round(v) + 'm' : (v / 1000).toFixed(1);
    return v < 1024 ? Math.round(v) + 'Mi' : (v / 1024).toFixed(1) + 'Gi';
  }
  // Snap to tidy steps: 5m / 4Mi at the bottom, coarser as values grow.
  function snap(res, v) {
    var step = res === 'cpu' ? (v < 100 ? 5 : v < 1000 ? 10 : 100) : (v < 128 ? 4 : v < 1024 ? 16 : 128);
    return Math.max(step, Math.round(v / step) * step);
  }
  function setup(row, d) {
    var res = row.dataset.res, lo = row.querySelector('.lo'), hi = row.querySelector('.hi');
    var pos = function (v) { return 1000 * Math.cbrt(Math.min(1, Math.max(0, v / d.top))); };
    var val = function (p) { return d.top * Math.pow(p / 1000, 3); };
    var top = Math.floor(d.top), floor = Math.min(top, Math.ceil(d.floor));
    function draw(moved) {
      var r = Math.min(snap(res, val(+lo.value)), top), l = Math.min(snap(res, val(+hi.value)), top);
      if (l < floor) l = floor;
      if (r > l) { if (moved === hi) r = l; else l = r; }
      lo.value = pos(r); hi.value = pos(l);
      row.querySelector('.req').textContent = fmt(res, r);
      row.querySelector('.lim').textContent = fmt(res, l);
      row.querySelector('[name=' + res + '_request]').value = r;
      row.querySelector('[name=' + res + '_limit]').value = l;
      var band = row.querySelector('.rl-band');
      band.style.left = pos(r) / 10 + '%'; band.style.width = Math.max(0, pos(l) - pos(r)) / 10 + '%';
      // Fill: usage on the same scale, coloured by how close it is to the limit.
      var fill = row.querySelector('.rl-fill'), f = Math.min(1, d.usage / l);
      fill.style.width = pos(d.usage) / 10 + '%';
      fill.style.background = 'hsl(' + Math.round(240 * (1 - f)) + ',85%,55%)';
      // Whichever thumb is nearer the pointer's side stays on top when they meet.
      lo.style.zIndex = +lo.value > 500 ? 3 : 2; hi.style.zIndex = +lo.value > 500 ? 2 : 3;
    }
    lo.value = pos(d.request); hi.value = pos(d.limit);
    lo.oninput = function () { draw(lo); }; hi.oninput = function () { draw(hi); };
    row.querySelector('.now').textContent = 'busiest container now: ' + fmt(res, d.usage);
    draw();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button.warn') : null;
    if (!b) return;
    fetch('/api/app/' + encodeURIComponent(b.dataset.ns) + '/resources', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (d) {
        form.action = '/app/' + encodeURIComponent(b.dataset.ns) + '/resources';
        document.getElementById('rl-app').textContent = b.dataset.app;
        form.restart.checked = false; err.textContent = '';
        dlg.querySelectorAll('.rl-row').forEach(function (row) { setup(row, d[row.dataset.res]); });
        dlg.showModal();
      })
      .catch(function (x) { alert('Could not load requests and limits (' + x + ')'); });
  });
  dlg.querySelector('.cancel').onclick = function () { dlg.close(); };
  dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
})();
</script>
"""

IMG_CSS = """
 dialog#im { border: 0; border-radius: 10px; padding: 22px 26px; width: min(720px, 94vw); max-height: 86vh;
   box-shadow: 0 12px 40px rgba(0,0,0,.3); font: 15px/1.4 system-ui, sans-serif; color: #222; }
 dialog#im::backdrop { background: rgba(20,30,45,.45); }
 #im h3 { margin: 0 0 4px; font-size: 20px; }
 #im p.note { margin: 0 0 14px; font-size: 13px; color: #666; }
 #im .im-list { display: flex; flex-direction: column; gap: 8px; }
 #im .im-w { padding: 10px 12px; background: #f5f6f8; border-radius: 8px; }
 #im .im-w .im-name { font-weight: 600; }
 #im .im-w .im-name small { font-weight: 400; color: #888; margin-left: 6px; font-size: 12px;
   text-transform: uppercase; letter-spacing: .5px; }
 #im .im-c { display: flex; align-items: center; gap: 10px; margin-top: 6px; font-size: 13px; }
 #im .im-c code { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; color: #444;
   font: 12px/1.4 ui-monospace, monospace; }
 #im .im-c form { display: flex; gap: 6px; margin: 0; flex: 0 0 auto; }
 #im .im-c select, #im .im-c button, #im .im-foot button { font-size: 13px; padding: 4px 10px; border-radius: 6px;
   border: 1px solid #d8dde5; background: #fff; cursor: pointer; }
 #im .im-c button { background: #1a4d8f; border-color: #1a4d8f; color: #fff; }
 #im .im-c button:disabled { background: #c9ced6; border-color: #c9ced6; cursor: default; }
 #im .im-foot { text-align: right; margin-top: 16px; }
"""

IMG_HTML = """
<dialog id="im">
 <h3>Images: <span id="im-app"></span></h3>
 <p class="note">Every workload in the app's namespace. Images from the mesh registry can be
 retagged: <b>latest</b>, then the five most recently built tags.</p>
 <div class="im-list"></div>
 <div class="im-foot"><button type="button" class="cancel">Close</button></div>
</dialog>
<script>
// Image menu: one block per workload, one line per container; a mesh-registry
// image gets a tag picker that posts to /app/<ns>/image.
(function () {
  var dlg = document.getElementById('im');
  if (!dlg || !dlg.showModal) return;
  var list = dlg.querySelector('.im-list');
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function hidden(form, name, value) {
    var i = el('input'); i.type = 'hidden'; i.name = name; i.value = value; form.appendChild(i);
  }
  function render(ns, workloads) {
    list.textContent = '';
    if (!workloads.length) list.appendChild(el('div', 'im-w', 'No workloads in this namespace.'));
    workloads.forEach(function (w) {
      var box = el('div', 'im-w'), name = el('div', 'im-name', w.name);
      name.appendChild(el('small', '', w.kind));
      box.appendChild(name);
      w.containers.forEach(function (c) {
        var row = el('div', 'im-c');
        row.appendChild(el('code', '', (w.containers.length > 1 ? c.name + ': ' : '') + c.image));
        if (c.tags && c.tags.length) {
          var form = el('form'); form.method = 'post';
          form.action = '/app/' + encodeURIComponent(ns) + '/image';
          hidden(form, 'kind', w.kind); hidden(form, 'name', w.name); hidden(form, 'container', c.name);
          var sel = el('select'); sel.name = 'tag';
          c.tags.forEach(function (t) {
            var o = el('option', '', t); o.value = t; o.selected = t === c.tag; sel.appendChild(o);
          });
          var go = el('button', '', 'Set'); go.disabled = true;
          sel.onchange = function () { go.disabled = sel.value === c.tag; };
          form.appendChild(sel); form.appendChild(go); row.appendChild(form);
        }
        box.appendChild(row);
      });
      list.appendChild(box);
    });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button.imgs') : null;
    if (!b) return;
    fetch('/api/app/' + encodeURIComponent(b.dataset.ns) + '/images', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (d) {
        document.getElementById('im-app').textContent = b.dataset.app;
        render(b.dataset.ns, d);
        dlg.showModal();
      })
      .catch(function (x) { alert('Could not load images (' + x + ')'); });
  });
  dlg.querySelector('.cancel').onclick = function () { dlg.close(); };
  dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
})();
</script>
"""

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
 ul.menu li .stat span {{ font-size: 10px; color: #999; text-transform: uppercase; letter-spacing: .5px; white-space: nowrap; }}
 ul.menu li .act {{ flex: 0 0 auto; margin: 0; width: 34px; text-align: center; }}
 ul.menu li .act button {{ cursor: pointer; border: 1px solid #d8dde5; border-radius: 6px; background: #fff;
                           width: 30px; height: 30px; font-size: 14px; line-height: 1; color: #777; }}
 ul.menu li .act.stop button:hover {{ background: #ffecec; border-color: #e0a0a0; color: #b00020; }}
 ul.menu li .act.start button:hover {{ background: #e8f5e9; border-color: #a0cfa5; color: #1b7f3b; }}
 ul.menu li .act + .act {{ margin-left: -12px; }}
 ul.menu li .act.restart button {{ font-size: 17px; }}
 ul.menu li .act.restart button:hover {{ background: #e8f0fb; border-color: #9db8dc; color: #1a4d8f; }}
 table {{ border-collapse: collapse; background: rgba(255,255,255,.85); width: 100%; font-size: 14px; }}
 th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #e3e3df; }}
 th {{ color: #666; font-weight: 600; }}
 pre {{ background: rgba(255,255,255,.85); padding: 12px; overflow-x: auto; font-size: 13px; }}
 pre.fortune {{ border-left: 3px solid #4682b4; padding: 10px 14px; margin: 8px 0 0;
                font-size: 13px; color: #555; font-style: italic; white-space: pre-wrap; }}
 .heat {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
 .ok {{ color: #1b7f3b; }} .bad {{ color: #b00020; }}
 footer {{ margin-top: 48px; color: #888; font-size: 13px; }}
{rl_css}</style></head><body><main>
<div class="hdr">
<nav><a href="/{ca_name}" download="{ca_name}" title="Cluster CA: trust this to stop the browser warnings">{ca_name}</a></nav>
<div class="corner"><div class="host">{host}</div>{auth_nav}</div>
</div>
<h1>Aviary</h1>
{fortune}
<h2>Apps</h2>
<ul class="menu">{menu}</ul>
{system}
<h2>Cluster</h2>
<table id="nodes"><thead><tr><th>Node</th><th>Role</th><th>Ready</th><th>Kubelet</th><th>CPU</th><th>Memory</th><th>Disk Cap</th><th>Disk Tput</th><th>Disk IOPS</th></tr></thead><tbody id="noderows">{nodes}</tbody></table>
<h2>/etc/hosts</h2>
<p>If your resolver does not know these names:</p>
<pre>{hosts}</pre>
<footer>Served by {me}</footer>
</main>
{rl_html}
<script>
// Keep the node table live without reloading the page: pull the <tbody> from
// /api/nodes (carrying the session cookie) and swap it in. Self-scheduling --
// the next fetch is queued 200ms after the previous one *finishes*, so a slow
// response can't let requests pile up. Silent on error so a transient blip just
// leaves the last-good rows on screen.
// (Braces are doubled because this page is rendered with str.format().)
(function () {{
  var tb = document.getElementById('noderows');
  if (!tb) return;
  function tick() {{
    fetch('/api/nodes', {{ credentials: 'same-origin' }})
      .then(function (r) {{ return r.ok ? r.text() : Promise.reject(r.status); }})
      .then(function (h) {{ tb.innerHTML = h; }})
      .catch(function () {{}})
      .finally(function () {{ setTimeout(tick, 200); }});
  }}
  tick();
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
    items, system_items = [], []
    m = d["metrics"]
    rels = d["releases"]
    for host, ns, svc, port, ip, group in d["routes"]:
        me_too = svc == "aviary-frontend"  # that's us: listed first under System
        label = host.split(".", 1)[0]
        blurb = "This page" if me_too else BLURBS.get(label, f"{ns}/{svc}:{port}")
        mem = _hbytes(m["mem"][ns]) if ns in m["mem"] else "-"
        cpu = _hcpu(m["cpu"][ns]) if ns in m["cpu"] else "-"
        disk = _hbytes(m["disk"][ns]) if ns in m["disk"] else "-"
        mem_top, cpu_top = m["mem_max"].get(ns), m["cpu_max"].get(ns)
        mem_heat = _heat(_frac(m["mem"].get(ns), mem_top), f"of {_hbytes(mem_top)} max" if mem_top else "")
        cpu_heat = _heat(_frac(m["cpu"].get(ns), cpu_top), f"of {_hcpu(cpu_top)} max" if cpu_top else "")
        gaps = m["unset"].get(ns)
        warn = ""
        if gaps:
            tip = "containers without: " + ", ".join(f"{k} ({n})" for k, n in sorted(gaps.items()))
            warn = (
                f'<button type="button" class="warn" data-ns="{html.escape(ns)}" '
                f'data-app="{html.escape(label)}" title="{html.escape(tip)} '
                f'&#10;click to set requests and limits">!</button>'
            )
        elif ns in m["tuned"]:
            # Nothing missing any more, but keep a way back to the sliders.
            warn = (
                f'<button type="button" class="warn set" data-ns="{html.escape(ns)}" '
                f'data-app="{html.escape(label)}" title="adjust requests and limits">&#8660;</button>'
            )
        rel = _release_for(ns, label, rels)
        off = bool(rel) and rels.get((ns, rel)) == "uninstalled"
        if not rel or me_too:
            # Not a helm release: no button. Nor for this page, which could not
            # be started again from a page that is no longer there.
            act = '<div class="act"></div>'
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
        # Restart sits to the right of stop; a stopped app has nothing to roll.
        restart = '<div class="act"></div>' if off else (
            f'<form class="act restart" method="post" action="/app/{html.escape(ns)}/restart">'
            f'<button title="restart (roll every workload in {html.escape(ns)})">&#8635;</button></form>'
        )
        images = (
            f'<div class="act images"><button type="button" class="imgs" data-ns="{html.escape(ns)}" '
            f'data-app="{html.escape(label)}" title="workloads and images">&#9776;</button></div>'
        )
        is_system = me_too or (group == "system" if group else label in SYSTEM)
        row = (
            f'<li class="{"off" if off else ""}"><div class="app">'
            f'<a href="https://{html.escape(host)}/">{html.escape(label)}</a>'
            f"<small>{html.escape(blurb)}</small></div>"
            f'<div class="stats">'
            f'<div class="stat"><b{cpu_heat}>{cpu}</b><span>CPU</span></div>'
            f'<div class="stat"><b{mem_heat}>{mem}</b><span>Memory</span></div>'
            f'<div class="stat"><b>{disk}</b><span>Disk Cap</span></div>'
            f'<div class="stat"><b>&mdash;</b><span>Disk Tput</span></div>'
            f'<div class="stat"><b>&mdash;</b><span>Disk IOPS</span></div>'
            f'</div><div class="act">{warn}</div>{act}{restart}{images}</li>'
        )
        if me_too:
            system_items.insert(0, row)
        else:
            (system_items if is_system else items).append(row)
    nodes_html = _node_rows_html(d["nodes"])
    by_ip = {}
    for host, _, _, _, ip, _ in d["routes"]:
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
        system=(
            f'<h2>System</h2>\n<ul class="menu">{"".join(system_items)}</ul>'
            if system_items else ""
        ),
        nodes=nodes_html,
        hosts=html.escape(hosts),
        me=html.escape(me),
        rl_css=RL_CSS + IMG_CSS,
        rl_html=RL_HTML + IMG_HTML,
    )


@app.route("/api/nodes")
def api_nodes():
    """The node table body, for the page's live refresh. Gated like the rest of
    the app (not a public path), so the browser's session cookie carries in."""
    response.content_type = "text/html; charset=utf-8"
    return _node_rows_html(nodes_snapshot())


@app.route("/api/app/<ns>/resources")
def api_app_resources(ns):
    """Current usage, scale and request/limit values for the popup's sliders."""
    if ns not in app_namespaces():
        raise HTTPError(404, "no such app\n")
    return app_resources(ns)


@app.route("/app/<ns>/resources", method="POST")
def app_resources_set(ns):
    """Save the popup: write the app's LimitRange (default request and limit for
    containers that set none) and, if asked, roll its workloads to apply it."""
    if ns not in app_namespaces():
        raise HTTPError(404, "no such app\n")
    cur = app_resources(ns)
    try:
        val = {k: int(request.forms.get(k, "")) for k in
               ("cpu_request", "cpu_limit", "mem_request", "mem_limit")}
    except ValueError:
        raise HTTPError(400, "requests and limits must be whole millicores / Mi\n")
    for key, name in (("cpu", "cpu"), ("mem", "memory")):
        r, l = val[f"{key}_request"], val[f"{key}_limit"]
        if not 0 < r <= l <= cur[key]["top"]:
            raise HTTPError(400, f"{name}: need 0 < request <= limit <= the largest node\n")
        if l < cur[key]["floor"]:
            raise HTTPError(400, f"{name}: a container here already requests more than that limit\n")
    body = {
        "apiVersion": "v1", "kind": "LimitRange",
        "metadata": {"name": LIMITRANGE, "namespace": ns,
                     "labels": {"app.kubernetes.io/managed-by": "aviary-frontend"}},
        "spec": {"limits": [{
            "type": "Container",
            "defaultRequest": {"cpu": f"{val['cpu_request']}m", "memory": f"{val['mem_request']}Mi"},
            "default": {"cpu": f"{val['cpu_limit']}m", "memory": f"{val['mem_limit']}Mi"},
        }]},
    }
    v1 = client.CoreV1Api()
    try:
        v1.replace_namespaced_limit_range(LIMITRANGE, ns, body)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise
        v1.create_namespaced_limit_range(ns, body)
    if request.forms.get("restart"):
        restart_workloads(ns)
    _bump()
    redirect("/")


@app.route("/api/app/<ns>/images")
def api_app_images(ns):
    """Workloads and their images, for the image menu."""
    if ns not in image_namespaces():
        raise HTTPError(404, "no such app\n")
    response.content_type = "application/json"
    return json.dumps(app_images(ns))


@app.route("/app/<ns>/image", method="POST")
def app_image_set(ns):
    """Retag one container of one workload (like kubectl set image). Only a
    mesh-registry image, and only to a tag the menu offered. For a
    helm-installed app the next helm upgrade puts the chart's tag back."""
    if ns not in image_namespaces():
        raise HTTPError(404, "no such app\n")
    kind, name = request.forms.get("kind", ""), request.forms.get("name", "")
    cname, tag = request.forms.get("container", ""), request.forms.get("tag", "")
    if kind not in _WORKLOAD_KINDS:
        raise HTTPError(400, "unknown workload kind\n")
    _, read, patch = _workload_api(kind)
    try:
        w = read(name, ns)
    except client.exceptions.ApiException as e:
        raise HTTPError(404 if e.status == 404 else 502, f"{kind} {name}: {e.reason}\n")
    for i, c in enumerate(w.spec.template.spec.containers):
        if c.name == cname:
            break
    else:
        raise HTTPError(404, f"no container {cname} in {kind} {name}\n")
    mesh = _mesh_image(c.image)
    if not mesh:
        raise HTTPError(400, f"only {IMAGE_REGISTRY} images can be retagged here\n")
    if tag not in image_tags(mesh[0]):
        raise HTTPError(400, f"{tag!r} is not an offered tag for {mesh[0]}\n")
    base = f"/spec/template/spec/containers/{i}"
    # JSON patch, guarded by a test on the container name so a concurrent
    # reorder cannot retag the wrong container.
    patch(name, ns, [
        {"op": "test", "path": f"{base}/name", "value": cname},
        {"op": "replace", "path": f"{base}/image", "value": f"{IMAGE_REGISTRY}/{mesh[0]}:{tag}"},
    ])
    _bump()
    redirect("/")


@app.route("/app/<ns>/restart", method="POST")
def app_restart(ns):
    """Restart an app: roll every workload in its namespace."""
    if ns not in app_namespaces():
        raise HTTPError(404, "no such app\n")
    restart_workloads(ns)
    _bump()
    redirect("/")


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
