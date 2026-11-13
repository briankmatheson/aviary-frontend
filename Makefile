# Build and push the landing page image; aviary-deploy's apps/aviary-frontend.tf
# pulls aviary_frontend_image (default briankmatheson/aviary-frontend:TAG).
#
#   make push                       # Docker Hub (HUB_USER)
#   make push REGISTRY=registry.example.net   # an internal registry
#
# With xdebbie on this box the mesh registry is picked up automatically:
# registry.<[network] domain in /etc/xdebbie/xdebbied.toml>.
HUB_USER  ?= briankmatheson
MESH_ZONE ?= $(shell sed -n 's/^domain *= *"\(.*\)"/\1/p' /etc/xdebbie/xdebbied.toml 2>/dev/null | head -1)
REGISTRY  ?= $(if $(MESH_ZONE),registry.$(MESH_ZONE),$(HUB_USER))
TAG       ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
IMAGE     := $(REGISTRY)/aviary-frontend:$(TAG)

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
	kubectl -n aviary rollout restart deployment aviary-frontend
	kubectl -n aviary rollout status deployment aviary-frontend
