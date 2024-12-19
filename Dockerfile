FROM debian

COPY app.py ca.crt aviary.png favicon.ico /
RUN apt update && apt -y install python3-bottle python3-kubernetes gunicorn 
CMD ["/usr/bin/gunicorn", "/app.py"]
