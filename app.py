from bottle import Bottle, route, run, template, static_file, debug
from kubernetes import client, config
import locale
import re

app = Bottle()

@app.route('/favicon.ico')
def favicon():
    return static_file('favicon.ico', root='./') 

@app.route('/aviary.png')
def logo():
    return static_file('aviary.png', root='./') 

@app.route('/ca.crt')
def ca():
    return static_file('ca.crt', root='./') 

style_header = """
<head><title>Aviary Platform</title>
<style>
ul {
  list-style-type: none;
  margin: 16;
  padding: 16;
  overflow: hidden;
  width: 40%;
  background-image: linear-gradient(DarkSlateGray, #f1fef1, #fafaf1);
}

lh {
  text-align: center;
  height: 42%;
  width: 90%;
  color: #fafaf1;
  display: block;
  float: center;
  vertical-align: top;
  background-position-x: center; 
  background-position-y: center; 
  background-image: url("aviary.png");
  background-repeat: no-repeat;
  background-size: 50%;
  background-float: right;
}

li a {
  display: block;
  color: Blue;
  text-align: left;
  text-decoration: none;
}

td small {
  color: gray;
  text-align: right;
  float: right;
  font-size: 70%;

}
li a:hover {
  color: #fafaf1;
  background-color: DarkSlateGray;
}
</style>
</head>
"""

menu = """
<body>
<a href="/ca.crt">ca</a>
<ul>
<lh><h1>Aviary</h1></lh>
<table>
<tr><td>
<li><a href="https://gitea">
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
<li><a href="https://harbor">
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
<li><a href="https://postgres-ui.local">
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
</table>
</ul>

"""

@app.route('/')
def index():
    namespace = "default"
    nodes = "<table>"
    ingresses = '<pre><small><p>---BEGIN /etc/hosts---</p><table style="font-size:65%">'
    
    #config.kube_config.load_kube_config()
    print("Listing pods with their IPs:")

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
        stats  = k8s_metrics['items'][i]
        node = k8s_nodes.items[i]

        cpu = int(re.sub(r'\D', '', stats['usage']['cpu'])) / int(re.sub(r'\D', '', node.status.capacity['cpu']))/1024/1024/1024 * 100
        mem = int(re.sub(r'\D', '', stats['usage']['memory'])) / int(re.sub(r'\D', '', node.status.allocatable['memory'])) * 100
        
        nodes += "<tr><td>Node Name:</td><td>%s\tCPU::</td><td>%3d%%</td><td>Memory: %3d%%</td></tr>" % (stats['metadata']['name'],
                                                                                                     cpu,
                                                                                                     mem)
    for ing in k8s_ing.items:
        ingresses += "<tr><td>%s\t</td><td>%s</td><td># %s:%d</td><td>(%s / %s)</td></tr>" % (ing.status.load_balancer.ingress[0].ip,
                                                                                             
                                                                                             ing.spec.rules[0].host,
                                                                                             ing.spec.rules[0].http.paths[0].backend.service.name,
                                                                                             ing.spec.rules[0].http.paths[0].backend.service.port.number,
                                                                                             ing.metadata.namespace,
                                                                                             ing.metadata.name)
    
    nodes += "</table>"
    ingresses += "</pre><br></table><p>---END---</p></small>"

    return style_header, menu, "<br>", nodes, "<br>", ingresses, "<hr></body></html>"


def main_app():
    try:
        config.load_incluster_config()
    except:
        print("Error: can\'t load incluster config, trying kubeconfig\n")
        config.kube_config.load_kube_config()

    run(app=app, debug=True, host='0.0.0.0', port=8080)

main_app()
