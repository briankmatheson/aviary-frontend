from bottle import Bottle, route, run, template, static_file, debug
from kubernetes import client, config


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
  width: 30%;
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

li {
  width: 100%;
  float: right;
}

li a {
  display: block;
  color: Blue;
  text-align: left;
  padding: 8px;
  width: 90%;
  text-decoration: none;
}

small {
  color: gray;
  text-align: right;
}
li a:hover {
  color: #fafaf1;
  background-color: DarkSlateGray;
  margin-right: 10px;
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
<small>Container Image Registdy</small>
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

</body>
</html>
"""

@app.route('/')
def index():
    namespace = "default"
    nodes = ""
    
    #config.kube_config.load_kube_config()
    print("Listing pods with their IPs:")
    try:
        api = client.CustomObjectsApi()
    except:
        raise
    k8s_nodes = api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")

    for stats in k8s_nodes['items']:
        nodes += "Node Name: %s\tCPU: %s\tMemory: %s" % (stats['metadata']['name'], stats['usage']['cpu'], stats['usage']['memory'])
        return style_header, menu, nodes


def main_app():
    try:
        config.load_incluster_config()
    except:
        raise
    run(app=app, debug=True, host='0.0.0.0', port=8080)

main_app()
