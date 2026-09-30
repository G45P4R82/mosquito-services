# Mosquito Services

Docker Compose deployment for Mosquitto MQTT with authenticated users and per-device ACLs.

## Requirements

- Docker Engine
- Docker Compose v2
- `make`

## First setup

```bash
cp .env.example .env
cp users/users.example users/users.txt
chmod 600 users/users.txt
make add
make up
```

`users/users.txt` uses one account per line:

```text
iot-sensor-001:uma-senha-forte
iot-sensor-002:outra-senha-forte
```

The file is ignored by Git. `make add` generates the Mosquitto password hashes in `config/passwd`, also ignored by Git. Do not commit either file.

## Commands

```bash
make up                 # start the service
make down               # stop and remove the container
make apply              # recreate the service with current configuration
make logs               # follow the last 100 log lines
make add                # read users/users.txt and update accounts
make add USERS_FILE=... # use another users file
make check              # validate the rendered Compose configuration
```

Run `make add` again after changing `users/users.txt`. It updates existing accounts and creates new ones.

## Topics

The default ACL gives each authenticated user access only to its own namespace:

```text
write: sensores/<username>/#
read:  comandos/<username>/#
```

For example, `iot-sensor-001` can publish to `sensores/iot-sensor-001/temperatura` and subscribe to `comandos/iot-sensor-001/#`.

Customize `config/acl` to define shared topics. Keep credentials and private certificates outside the public repository.

## Connection

The default MQTT endpoint is `mqtt://HOST:1883`. TLS on port 8883 is not enabled by default; it should be added before exposing the broker directly to the Internet.
