# Build and push the landing page image; aviary-deploy's apps/aviary-frontend.tf
# pulls REGISTRY/aviary-frontend:TAG.
REGISTRY ?= registry.mesh.harlem.bmath.nyc
TAG      ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
IMAGE    := $(REGISTRY)/aviary-frontend:$(TAG)

.PHONY: build push run rollout

build:
	docker build --network=host -t $(IMAGE) -t $(REGISTRY)/aviary-frontend:latest .

push: build
	docker push $(IMAGE)
	docker push $(REGISTRY)/aviary-frontend:latest
	@echo "$(IMAGE)"

## Run locally against the current kubeconfig
run:
	PORT=8086 python3 app.py

## Restart the deployment so it pulls :latest again
rollout:
	kubectl -n kube-system rollout restart deployment aviary-frontend
	kubectl -n kube-system rollout status deployment aviary-frontend
