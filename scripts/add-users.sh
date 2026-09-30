#!/bin/sh
set -eu

users_file="${USERS_FILE:-users/users.txt}"
password_file="/mosquitto/config/passwd"

if [ ! -f "$users_file" ]; then
    printf 'Arquivo de usuarios nao encontrado: %s\n' "$users_file" >&2
    printf 'Crie-o usando o formato usuario:senha, uma conta por linha.\n' >&2
    exit 1
fi

if [ ! -s "$users_file" ]; then
    printf 'Arquivo de usuarios vazio: %s\n' "$users_file" >&2
    exit 1
fi

while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        ''|'#'*) continue ;;
    esac

    username=${line%%:*}
    password=${line#*:}

    if [ "$username" = "$line" ] || [ -z "$username" ] || [ -z "$password" ]; then
        printf 'Linha invalida no arquivo de usuarios: %s\n' "$line" >&2
        exit 1
    fi

    case "$username" in
        *[!A-Za-z0-9_.-]*)
            printf 'Usuario invalido: %s\n' "$username" >&2
            exit 1
            ;;
    esac

    printf 'Atualizando usuario %s\n' "$username"
    printf '%s\n%s\n' "$password" "$password" |
        docker compose run --rm --no-deps --user 0 -T mosquitto \
        mosquitto_passwd "$password_file" "$username"
done < "$users_file"

docker compose run --rm --no-deps --user 0 -T mosquitto \
    chown root:root "$password_file"

docker compose run --rm --no-deps --user 0 -T mosquitto \
    chmod 644 "$password_file"
