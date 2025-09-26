from bottle import Bottle, route, run, template, static_file, debug
from kubernetes import client, config
import locale
import re
import base64
import requests

app = Bottle()

@app.route('/favicon.ico')
def favicon():
    return static_file('aviary004.png', root='./') 

@app.route('/aviary.png')
def logo():
    return static_file('aviary004.png', root='./') 

@app.route('/ca')
def ca():
    try:
        k8s_api = client.CoreV1Api()
    except:
        raise

    secret = k8s_api.read_namespaced_secret("ca-secret", "cert-manager")
    aviary_ca_cert = base64.b64decode(secret.data["ca.crt"]).decode("utf-8")
    return aviary_ca_cert

@app.route('/token')
def token():
    token_request = client.AuthenticationV1TokenRequest(
        spec=client.V1TokenRequestSpec(
                        expiration_seconds=3600,
                        audiences=["https://aviary.local"]))
    auth_client = client.AuthenticationV1Api()
    response = auth_client.create_namespaced_service_account_token(
        name="dash",      # service account name
        namespace="default", # namespace
        body=token_request
    )
    return response.status.token


style_header = """
<head><title>Aviary Platform</title>

<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
<meta http-equiv="Pragma" content="no-cache" />
<meta http-equiv="Expires" content="0" /><style>

ul {
  list-style-type: none;
  margin: 6;
  padding 6;
  overflow: hidden;
  width: 72%;
  background-color: gray92;
  background-float: center;
  opacity: .9;
}

div {
  background-position-x: left; 
  background-position-y: top; 
  background-image: url("https://aviary.local/aviary.png");
  background-repeat: no-repeat;
  background-size: 72%;
  background-float: right;
  opacity: .69;
}


div {
  table {
    background-color: gray92;
  }
}

li {
  background-color: gray82;
  padding: 16;
}


li a {
  display: block;
  color: Blue;
  weight: bold;
  text-align: left;
  text-decoration: none;
  font-size: 200%;
}

td small {
  opacity: 1
  color: black;
  weight: bold;
  text-align: right;
  float: left;
  font-size: 120%;

}
li a:hover {
  color: lightyellow;
  background-color: DarkSlateGray;
}
</style>
</head>
"""

menu = """
<body>
<div>
<ul>
<lh><h1>Aviary</h1></lh>
<table>
<tr><td>

<li><a href="https://ca.crt">
aviary-ca.crt</a></li>
</td><td>
<small>CA Cert for signing ingress tls</small>
</td></tr>

<tr><td>
<li><a href="https:/token">
default:default token</a></li>
</td><td>
<small>token for use in dashboard, etc.</small>
</td></tr>

<br>

<tr><td>
>>>>>>> de514a1 (fixes for .local)
<li><a href="https://gitea.local">
gitea</a></li>
</td><td>
<small>Source Code Management</small>
</td></tr>
 
<tr><td>
<li><a href="https://drone.local">
drone</a></li>
</td><td>
<small>Continous Integration</small>
</td></tr>

<tr><td>
<li><a href="https://harbor.local">
harbor</a></li>
</td><td>
<small>Container Image Registry</small>
</td></tr>

<br>

<tr><td>
<li><a href="https://jupyterhub.local">
jupyterhub</a></li>
</td><td>
<small>Interactive Notebook Server</small>
</td></tr>

<tr><td>
<li><a href="https://mlflow.local">
mlflow</a></li>
</td><td>
<small>Machine Learning Lifecycle Management</small>
</td></tr>

<br>

<tr><td>
<li><a href="https://pgui.local">
postgres-ui</a></li>
</td><td>
<small>Relational Database</small>
</td></tr>

<tr><td>
<li><a href="https://minio.local">
minio</a></li>
</td><td>
<small>Object Store</small>
</td></tr>

<br>

<tr><td>
<li><a href="https://bash.local">
BASH</a></li>
</td><td>
<small>In-Cluster Bourne Shell</small>
</td></tr>

<tr><td>
<li><a href="https://rustpad.local">
rustpad</a></li>
</td><td>
<small>Shared Text Editor</small>
</td></tr>


<br>

<tr><td>
<li><a href="https://grafana.local">
grafana</a></li>
</td><td>
<small>Metrics Visualization and Alerting</small>
</td></tr>
<tr><td>
<li><a href="https://kubernetes-dashboard.local">
dashboard</a></li>
</td><td>
<small>Kubernetes Dashboard</small>
</td></tr>
</table>
</ul>
</div>

"""

@app.route('/')
def index():
    namespace = "default"
    nodes = "<table>"
    ingresses = '<pre><small><p>---BEGIN /etc/hosts---</p><table style="font-size:65%">'
    my_ip = "<h3>My SRC IP: "
    
    #config.kube_config.load_kube_config()
    print("<h2>Cluster:</h2>")

    try:
        k8s_api = client.CoreV1Api()
        metrics_api = client.CustomObjectsApi()
        net_api = client.NetworkingV1Api()
    except:
        raise
    
    k8s_metrics = metrics_api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
    k8s_nodes = k8s_api.list_node()
    k8s_ing = net_api.list_ingress_for_all_namespaces(pretty=True)

    for i in range(0, len(k8s_nodes.items)):
        try:
            stats = k8s_metrics['items'][i]
        except:
            stats['usage']['cpu'] = "0"
            stats['usage']['memory'] = "0"
            
        node = k8s_nodes.items[i]

        cpu = int(re.sub(r'\D', '', stats['usage']['cpu'])) / int(re.sub(r'\D', '', node.status.capacity['cpu']))/1024/1024/1024 * 100
        mem = int(re.sub(r'\D', '', stats['usage']['memory'])) / int(re.sub(r'\D', '', node.status.allocatable['memory'])) * 100
        
        nodes += "<tr><td>Node Name: %s</td><td>CPU: %3d%%</td><td>Memory: %3d%%</td></tr>" % (stats['metadata']['name'],
                                                                                                     cpu,
                                                                                                     mem)
    for ing in k8s_ing.items:
        ingresses += "<tr><td>%s\t</td><td>%s</td><td># %s:%s</td><td>(%s / %s)</td></tr>" % (ing.status.load_balancer.ingress[0].ip,
                                                                                             
                                                                                             ing.spec.rules[0].host,
                                                                                             ing.spec.rules[0].http.paths[0].backend.service.name,
                                                                                             ing.spec.rules[0].http.paths[0].backend.service.port.number,
                                                                                             ing.metadata.namespace,
                                                                                             ing.metadata.name)


    ip = requests.get('https://api.ipify.org')
    my_ip += ip.text
    
    nodes += "</table>"
    ingresses += "</pre><br></table><p>---END---</p></small>"
    my_ip += "</h3><br>\n"

    return style_header, menu, "<br>", nodes, "<br>", ingresses, "<hr></body></html>"


def main_app():
    try:
        config.load_incluster_config()
    except:
        print("Error: can\'t load incluster config, trying kubeconfig\n")
        config.kube_config.load_kube_config()

    run(app=app, debug=True, host='0.0.0.0', port=8080)

main_app()
