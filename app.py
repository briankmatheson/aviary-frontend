from bottle import route, run, template, static_file


@route('/favicon.ico')
def favicon():
    return static_file('favicon.ico', root='./') 

@route('/aviary.png')
def logo():
    return static_file('aviary.png', root='./') 

@route('/ca.crt')
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
  width: 20%;
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
  background-size: 70%;
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
<ul>

<lh><h1>Aviary Platform</h1></lh>

<li><a href="https://gitea">
<table><tr><td>
gitea
</td><td><small>
Source Code Management
</small></td><tr></a></li>

<li><a href="https://drone.local">
<table><tr><td>
drone
</td><td><small>
Continous Integration
</small></td><tr></a></li>

<li><a href="https://harbor">
<table><tr><td>
harbor
</td><td><small>
Container Image Registry
</small></td><tr></a></li>

<br>

<li><a href="https://jupyterhub.local">
<table><tr><td>
jupyterhub
</td><td><small>
Interactive Notebook Server
</small></td><tr></a></li>

<li><a href="https://mlflow.local">
<table><tr><td>
mlflow
</td><td><small>
Machine Learning Lifecycle Management
</small></td><tr></a></li>

<br>

<li><a href="https://postgres-ui.local">
<table><tr><td>
postgres-ui
</td><td><small>
Relational Database
</small></td><tr></a></li>

<li><a href="https://minio.local">
<table><tr><td>
minio</a></li>
</td><td><small>
Object Store
</small></td><tr></a></li>

<br>

<li><a href="https://bash.local">
<table><tr><td>
BASH
</td><td><small>
In-Cluster Bourne Shell
</small></td><tr></a></li>

<li><a href="https://rustpad.local">
<table><tr><td>
rustpad
</td><td><small>
Shared Text Editor
</small></td><tr></a></li>


<br>

<li><a href="https://grafana.local">
<table><tr><td>
grafana</a></li>
</td><td><small>
Metrics Visualization and Alerting
</small></td><tr></a></li>

</ul>
<a href="/ca.crt">ca</a>
</body>
</html>
"""

@route('/')
def index():
    return style_header, menu


def app():
    run(host='0.0.0.0', port=8080)

app()
