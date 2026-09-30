#!/usr/bin/env python3
"""User lifecycle and concurrent MQTT stress tests."""

import os
import subprocess
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import paho.mqtt.client as mqtt


class UserStressTest(unittest.TestCase):
    host = os.getenv("MQTT_TEST_HOST", "127.0.0.1")
    port = int(os.getenv("MQTT_TEST_PORT", "1883"))
    compose = ["docker", "compose"]
    password_file = "/mosquitto/config/passwd"
    host_users_file = Path("config/.stress-users")

    def run_passwd_batch(self, operation: str):
        command = """
set -eu
if [ "$1" = create ]; then
    : > /mosquitto/config/passwd
    while IFS=: read -r username password; do
        [ -z "$username" ] && continue
        printf '%s\\n%s\\n' "$password" "$password" | \
            mosquitto_passwd /mosquitto/config/passwd "$username"
    done < /mosquitto/config/.stress-users
else
    while IFS=: read -r username password; do
        [ -z "$username" ] && continue
        mosquitto_passwd -D /mosquitto/config/passwd "$username"
    done < /mosquitto/config/.stress-users
fi
chown root:root /mosquitto/config/passwd
chmod 644 /mosquitto/config/passwd
"""
        subprocess.run(
            self.compose
            + [
                "run",
                "--rm",
                "--no-deps",
                "--user",
                "0",
                "-T",
                "mosquitto",
                "sh",
                "-c",
                command,
                "batch",
                operation,
            ],
            check=True,
        )
        subprocess.run(self.compose + ["restart", "mosquitto"], check=True)
        time.sleep(1)

    def write_users(self, count: int, level: int):
        users = [
            (f"stress-{level}-{index:03d}", f"stress-password-{level}-{index:03d}")
            for index in range(count)
        ]
        self.host_users_file.write_text("\n".join(f"{user}:{password}" for user, password in users) + "\n")
        self.host_users_file.chmod(0o600)
        return users

    def mqtt_round_trip(self, user: tuple[str, str], level: int):
        username, password = user
        topic = f"sensores/{username}/stress/{level}"
        received = threading.Event()
        errors = []
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"stress-client-{username}",
        )
        client.username_pw_set(username, password)

        def on_connect(instance, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                errors.append(f"connect: {reason_code}")
                return
            instance.subscribe(topic, qos=1)

        def on_message(instance, userdata, message):
            if message.topic == topic:
                received.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self.host, self.port, keepalive=30)
        client.loop_start()
        time.sleep(0.2)
        info = client.publish(topic, f'{{"user":"{username}"}}', qos=1)
        info.wait_for_publish(timeout=10)
        delivered = received.wait(10)
        client.loop_stop()
        client.disconnect()
        if errors:
            raise AssertionError(f"{username}: {errors[0]}")
        if not info.is_published() or not delivered:
            raise AssertionError(f"{username}: message was not delivered")

    def assert_user_rejected(self, user: tuple[str, str]):
        username, password = user
        connected = threading.Event()
        result = []
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"deleted-user-check-{username}",
        )
        client.username_pw_set(username, password)

        def on_connect(instance, userdata, flags, reason_code, properties):
            result.append(reason_code)
            connected.set()

        client.on_connect = on_connect
        client.connect(self.host, self.port, keepalive=10)
        client.loop_start()
        self.assertTrue(connected.wait(10), username)
        client.loop_stop()
        client.disconnect()
        self.assertTrue(result[0].is_failure, f"deleted user still authenticated: {username}")

    def test_create_stress_delete_10_users(self):
        self.run_user_lifecycle(10)

    def test_create_stress_delete_20_users(self):
        self.run_user_lifecycle(20)

    def test_create_stress_delete_30_users(self):
        self.run_user_lifecycle(30)

    def test_create_stress_delete_40_users(self):
        self.run_user_lifecycle(40)

    def test_create_stress_delete_50_users(self):
        self.run_user_lifecycle(50)

    def run_user_lifecycle(self, count: int):
        level = count
        users = self.write_users(count, level)
        try:
            self.run_passwd_batch("create")
            with ThreadPoolExecutor(max_workers=count) as executor:
                jobs = [executor.submit(self.mqtt_round_trip, user, level) for user in users]
                for job in jobs:
                    job.result()

            self.run_passwd_batch("delete")
            with ThreadPoolExecutor(max_workers=count) as executor:
                jobs = [executor.submit(self.assert_user_rejected, user) for user in users]
                for job in jobs:
                    job.result()
        finally:
            self.restore_baseline_users()
            self.host_users_file.unlink(missing_ok=True)

    def restore_baseline_users(self):
        baseline = Path("users/users.txt")
        if not baseline.exists():
            return
        self.host_users_file.write_text(baseline.read_text())
        self.run_passwd_batch("create")


if __name__ == "__main__":
    unittest.main(verbosity=2)
