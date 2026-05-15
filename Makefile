PYTHON ?= python
MANAGE := $(PYTHON) manage.py

IMAGE ?= spotter-backend
TAG ?= local
PORT ?= 8000
HOST_PORT ?= 8000
DATA_VOLUME ?= spotter-data
SPOTTER_SECRET_KEY ?= replace-this-secret
SPOTTER_ALLOWED_HOSTS ?= localhost,127.0.0.1

.PHONY: help install migrate import-fuel-prices import-fuel-prices-geocode run check test collectstatic docker-build docker-run docker-run-no-import docker-run-import docker-run-import-geocode

help:
	@echo "Available targets:"
	@echo "  make install                    Install Python dependencies"
	@echo "  make migrate                    Run Django migrations"
	@echo "  make import-fuel-prices         Import CSV without external station geocoding"
	@echo "  make import-fuel-prices-geocode Import CSV and geocode pending stations"
	@echo "  make run                        Run local Django development server"
	@echo "  make check                      Run Django system checks"
	@echo "  make test                       Run pytest"
	@echo "  make collectstatic              Collect static files for production"
	@echo "  make docker-build               Build production Docker image"
	@echo "  make docker-run                 Run container, migrate, import fuel CSV, and serve API"
	@echo "  make docker-run-no-import       Run container without importing fuel CSV on startup"
	@echo "  make docker-run-import          Run container and force fuel CSV import on startup"
	@echo "  make docker-run-import-geocode  Run container, import CSV, and geocode pending stations"

install:
	$(PYTHON) -m pip install -r requirements.txt

migrate:
	$(MANAGE) migrate

import-fuel-prices:
	$(MANAGE) import_fuel_prices fuel-prices-for-be-assessment.csv --skip-geocoding

import-fuel-prices-geocode:
	$(MANAGE) import_fuel_prices fuel-prices-for-be-assessment.csv

run:
	$(MANAGE) runserver 127.0.0.1:$(PORT)

check:
	$(MANAGE) check

test:
	pytest

collectstatic:
	SPOTTER_DEBUG=false $(MANAGE) collectstatic --noinput

docker-build:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm -p $(HOST_PORT):$(PORT) \
		-e PORT=$(PORT) \
		-e SPOTTER_SECRET_KEY='$(SPOTTER_SECRET_KEY)' \
		-e SPOTTER_ALLOWED_HOSTS='$(SPOTTER_ALLOWED_HOSTS)' \
		-v $(DATA_VOLUME):/app/data \
		$(IMAGE):$(TAG)

docker-run-no-import:
	docker run --rm -p $(HOST_PORT):$(PORT) \
		-e PORT=$(PORT) \
		-e SPOTTER_SECRET_KEY='$(SPOTTER_SECRET_KEY)' \
		-e SPOTTER_ALLOWED_HOSTS='$(SPOTTER_ALLOWED_HOSTS)' \
		-e SPOTTER_IMPORT_FUEL_PRICES=false \
		-v $(DATA_VOLUME):/app/data \
		$(IMAGE):$(TAG)

docker-run-import:
	docker run --rm -p $(HOST_PORT):$(PORT) \
		-e PORT=$(PORT) \
		-e SPOTTER_SECRET_KEY='$(SPOTTER_SECRET_KEY)' \
		-e SPOTTER_ALLOWED_HOSTS='$(SPOTTER_ALLOWED_HOSTS)' \
		-e SPOTTER_IMPORT_FUEL_PRICES=true \
		-v $(DATA_VOLUME):/app/data \
		$(IMAGE):$(TAG)

docker-run-import-geocode:
	docker run --rm -p $(HOST_PORT):$(PORT) \
		-e PORT=$(PORT) \
		-e SPOTTER_SECRET_KEY='$(SPOTTER_SECRET_KEY)' \
		-e SPOTTER_ALLOWED_HOSTS='$(SPOTTER_ALLOWED_HOSTS)' \
		-e SPOTTER_IMPORT_FUEL_PRICES=true \
		-e SPOTTER_IMPORT_FUEL_PRICES_GEOCODE=true \
		-v $(DATA_VOLUME):/app/data \
		$(IMAGE):$(TAG)
