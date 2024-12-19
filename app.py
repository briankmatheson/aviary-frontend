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
<li><a title="Git Repo" href="https://gitea">gitea</a></li>
<li><a title="CI" href="https://drone.local">drone</a></li>
<li><a title="Registry" href="https://harbor">harbor</a></li>
<hr>
<li><a title="Interactive Notebook" href="https://jupyterhub.local">jupyterhub</a></li>
<li><a title="Model Tracking" href="https://mlflow.local">mlflow</a></li>
<hr>
<li><a title="RDBMS" href="https://postgres-ui.local">postgres-ui</a></li>
<li><a title="Object Store" href="https://minio.local">minio</a></li>
<li><a title="In-Cluster Shell" href="https://bash.local">cloudshell</a></li>
<li><a title="Shared Editor" href="https://rustpad.local">rustpad</a></li>
<hr>
<li><a title="Metrics and Alerting" href="https://grafana.local">grafana</a></li>
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
