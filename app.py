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

<table>
<td><tr>
<li><a href="https://gitea">
gitea</a></li>
</tr><tr>
Source Code Management
</tr></td>

<td><tr>
<li><a href="https://drone.local">
drone</a></li>
</tr><tr>
Continous Integration
</tr></td>

<td><tr>
<li><a href="https://harbor">
harbor</a></li>
</tr><tr>
Container Image Registry
</tr></td>

<br>

<td><tr>
<li><a href="https://jupyterhub.local">
jupyterhbu</a></li>
</tr><tr>
Interactive Notebook Server
</tr></td>

<td><tr>
<li><a href="https://mlflow.local">
mlflow</a></li>
</tr><tr>
Machine Learning Lifecycle Management
</tr></td>

<br>

<td><tr>
<li><a href="https://postgres-ui.local">
postgres-ui</a></li>
</tr><tr>
Relational Database
</tr></td>

<td><tr>
<li><a href="https://minio.local">
minio</a></li>
</tr><tr>
Object Store
</tr></td>

<br>

<td><tr>
<li><a href="https://bash.local">
BASH</a></li>
</tr><tr>
In-Cluster Bourne Shell
</tr></td>

<td><tr>
<li><a href="https://rustpad.local">
rustpad</a></li>
</tr><tr>
Shared Text Editor
</tr></td>


<br>

<td><tr>
<li><a href="https://grafana.local">
grafana</a></li>
</tr><tr>
Metrics Visualization and Alerting
</tr></td>

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
