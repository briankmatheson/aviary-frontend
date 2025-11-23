all: ca.crt 

ca.crt:
	eval echo `kubectl get secret -n cert-manager -o yaml ca-secret | yq '.data."ca.crt"'` | base64 -d > ca.crt

commit:
	git commit -am.

push:
	git push

build: 
	drone build create bmath/aviary-frontend
	sleep 6
	watch -q5 drone build info bmath/aviary-frontend
	watch -g drone build info bmath/aviary-frontend

rollout:
	kubectl rollout restart deployment aviary-frontend
	watch -d kubectl get pods
