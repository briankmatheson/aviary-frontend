FROM debian

COPY app.py ca.crt /
RUN apt update && apt -y install python3-bottle gunicorn
CMD ["/usr/bin/gunicorn", "/app.py"]
