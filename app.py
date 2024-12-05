from bottle import route, run, template

style_header = """
<head>
<style>
ul {
  list-style-type: none;
  margin: 16;
  padding: 16;
  overflow: hidden;
  background-color: LightGreen;
  width: 30%;
}

lh {
  float: center;
  text-align: right;
  height: 150px;
  color: NavajoWhite;
}

li {
  width: 100%;
  float: right;
}

li a {
  display: block;
  color: Gray90;
  text-align: left;
  padding: 8px;
  width: 100px;
  text-decoration: none;
}

li a:hover {
  color: NavajoWhite;
  background-color: DarkSlateGray;
  margin-right: 10px;
}
</style>
</head>
"""

menu = """
<body>
<ul >
<lh><center><h1>Aviary</h1></center></lh>
<li></li>
<li><a href="https://gitea">gitea</a></li>
<li><a href="https://drone.local">drone</a></li>
<li><a href="https://harbor">harbor</a></li>
<li><a href="https://jupyterhub.local">jupyterhub</a></li>
<li><a href="https://mlflow.local">mlflow</a></li>
<li><a href="https://postgres-ui.local">postgres-ui</a></li>
<li><a href="https://minio.local">minio</a></li>
<li><a href="https://bash.local">cloudshell</a></li>
<li><a href="https://rustpad.local">rustpad</a></li>
<li><a href="https://grafana.local">grafana</a></li>
</ul>
</body>
</html>
"""

@route('/')
def index():
    return style_header, menu

run(host='0.0.0.0', port=8080)

