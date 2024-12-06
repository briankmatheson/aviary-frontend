from bottle import route, run, template, static_file


@route('/favicon.ico')
def favicon():
    return static_file('favicon.ico', root='./') 

@route('/aviary.png')
def favicon():
    return static_file('aviary.png', root='./') 

style_header = """
<head><title>Aviary Platform</title>
<style>
ul {
  list-style-type: none;
  margin: 16;
  padding: 16;
  overflow: hidden;
  width: 20%;
  background-image: linear-gradient(DarkSlateGray, LightGreen, NavajoWhite
);
}

lh {
  text-align: center;
  height: 42%;
  width: 90%;
  color: NavajoWhite;
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
  color: NavajoWhite;
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

