all: build 


build:
	git commit -am.
	git push
	drone build create bmath/aviary-frontend
	sleep 6
	watch -q5 drone build info bmath/aviary-frontend
	watch -g drone build info bmath/aviary-frontend

rollout:
	kubectl rollout restart deployment aviary-frontend
	watch -d kubectl get pods
