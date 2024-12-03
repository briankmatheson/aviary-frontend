from bottle import route, run, template

menu = """
 '<b>Aviary Platform</b>'
<p>
<ul>
<li><a href="https://gitea.local">gitea</a></li>
<li><a href="https://drone.local">drone</a></li>
<li><a href="https://harbor.local">harbor</a></li
<li><a href="https://jupyterhub.local">jupyterhub</a></li>
<li><a href="https://harbor.local">harbor</a></li>
<li><a href="https://mlflow.local">mlflow</a></li>
<li><a href="https://postgres-ui.local">postgres-ui</a></li>
<li><a href="https://minio.local">minio</a></li>

"""

@route('/')
def index():
    return menu

run(host='0.0.0.0', port=8080)

