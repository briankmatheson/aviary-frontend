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

<li><a https://gitea">
<table><tr><td>
gitea
</td><td>
Source Code Management
</td><tr></a></li>

<li><a href="https://drone.local">
<table><tr><td>
drone
</td><td>
Continous Integration
</td><tr></a></li>

<li><a href="https://harbor">
<table><tr><td>
harbor
</td><td>
Container Image Registry
</td><tr></a></li>

<br>

<li><a href="https://jupyterhub.local">
<table><tr><td>
jupyterhub
</td><td>
Interactive Notebook Server
</td><tr></a></li>

<li><a href="https://mlflow.local">
<table><tr><td>
mlflow
</td><td>
Machine Learning Lifecycle Management
</td><tr></a></li>

<br>

<li><a href="https://postgres-ui.local">
<table><tr><td>
postgres-ui
</td><td>
Relational Database
</td><tr></a></li>

<li><a href="https://minio.local">
<table><tr><td>
minio</a></li>
</td><td>
Object Store
</td><tr></a></li>

<br>

<li><a href="https://bash.local">
<table><tr><td>
BASH
</td><td>
In-Cluster Bourne Shell
</td><tr></a></li>

<li><a href="https://rustpad.local">
<table><tr><td>
rustpad
</td><td>
Shared Text Editor
</td><tr></a></li>


<br>

<li><a href="https://grafana.local">
<table><tr><td>
grafana</a></li>
</td><td>
Metrics Visualization and Alerting
</td><tr></a></li>

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
