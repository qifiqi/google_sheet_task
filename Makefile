IMAGE_NAME := google_task
VERSION    := 1.0.5
TAR        := $(IMAGE_NAME)_$(VERSION).tar
TAR_GZ     := $(TAR).gz
REMOTE     := user@production-server
REMOTE_DIR := /path/

.PHONY: build save compress load deploy clean

build:
	docker build -t $(IMAGE_NAME):$(VERSION) .

save: build
	docker save -o $(TAR) $(IMAGE_NAME):$(VERSION)

compress: save
	gzip -f $(TAR)

scp: compress
	scp $(TAR_GZ) $(REMOTE):$(REMOTE_DIR)

load:
	docker load -i $(TAR)

deploy: load
	docker compose up -d

clean:
	rm -f $(TAR) $(TAR_GZ)