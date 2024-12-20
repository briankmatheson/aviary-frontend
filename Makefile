all: build 


build:
	git commit -am.
	git push
	drone build create bmath/aviary-frontend
	sleep 6
	watch drone build info bmath/aviary-frontend

rollout:
	kubectl rollout restart deployment aviary-frontend
	watch kubectl get pods
