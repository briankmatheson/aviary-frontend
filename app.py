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
  text-align: right
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

<lh><h1>Aviary</h1></lh>
<small>
<table>
<tr><td>
<li><a href="https://gitea">
gitea</a></li>
</td><td>
Source Code Management
</td></tr>

<tr><td>
<li><a href="https://drone.local">
drone</a></li>
</td><td>
Continous Integration
</td></tr>

<tr><td>
<li><a href="https://harbor">
harbor</a></li>
</td><td>
Container Image Registdy
</td></tr>

<br>

<tr><td>
<li><a href="https://jupyterhub.local">
jupyterhub</a></li>
</td><td>
Interactive Notebook Server
</td></tr>

<tr><td>
<li><a href="https://mlflow.local">
mlflow</a></li>
</td><td>
Machine Learning Lifecycle Management
</td></tr>

<br>

<tr><td>
<li><a href="https://postgres-ui.local">
postgres-ui</a></li>
</td><td>
Relational Database
</td></tr>

<tr><td>
<li><a href="https://minio.local">
minio</a></li>
</td><td>
Object Store
</td></tr>

<br>

<tr><td>
<li><a href="https://bash.local">
BASH</a></li>
</td><td>
In-Cluster Bourne Shell
</td></tr>

<tr><td>
<li><a href="https://rustpad.local">
rustpad</a></li>
</td><td>
Shared Text Editor
</td></tr>


<br>

<tr><td>
<li><a href="https://grafana.local">
grafana</a></li>
</td><td>
Metdics Visualization and Alerting
</td></tr>
</table>
</small>

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
