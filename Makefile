SHELL := /bin/sh

COMPOSE := docker compose
USERS_FILE ?= users/users.txt

.PHONY: up down apply logs add config check

up: config
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

apply: config
	$(COMPOSE) up -d --force-recreate

logs:
	$(COMPOSE) logs -f --tail=100 mosquitto

config:
	mkdir -p config data log
	touch config/passwd
	chmod 640 config/passwd

check:
	$(COMPOSE) config

add: config
	USERS_FILE="$(USERS_FILE)" ./scripts/add-users.sh
	$(COMPOSE) restart mosquitto
