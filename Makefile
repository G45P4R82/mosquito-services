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
	mkdir -p config data
	[ -f config/passwd ] || touch config/passwd
	$(COMPOSE) run --rm --no-deps --user 0 -T mosquitto sh -c 'chown -R 1883:1883 /mosquitto/data && chown root:root /mosquitto/config/passwd && chmod 644 /mosquitto/config/passwd'

check:
	$(COMPOSE) config

add: config
	USERS_FILE="$(USERS_FILE)" ./scripts/add-users.sh
	$(COMPOSE) up -d --force-recreate
