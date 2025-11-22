all: build rollout

aviary.crt:
	echo | awk "{print `kubectl get cm -n kube-public -o yaml kube-root-ca.crt | yq '.data."ca.crt"'`}" > aviary.crt

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
