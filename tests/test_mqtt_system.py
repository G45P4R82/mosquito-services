#!/usr/bin/env python3
"""Integration test: 10 publishers send data to 2 authenticated subscribers."""

import argparse
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt


def load_users(path: Path) -> list[tuple[str, str]]:
    users = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        username, password = line.split(":", 1)
        users.append((username, password))
    if len(users) < 2:
        raise ValueError("users file must contain at least two users")
    return users[:2]


class Receiver:
    def __init__(self, host: str, port: int, username: str, password: str, expected: int):
        self.username = username
        self.expected = expected
        self.messages: list[str] = []
        self.connected = threading.Event()
        self.finished = threading.Event()
        self.error = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-receiver-{username}")
        self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.host = host
        self.port = port

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.error = f"{self.username}: connection failed: {reason_code}"
            return
        result, _ = client.subscribe(f"sensores/{self.username}/#", qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.error = f"{self.username}: subscribe failed: {result}"
            return
        self.connected.set()

    def on_message(self, client, userdata, message):
        self.messages.append(message.payload.decode())
        if len(self.messages) >= self.expected:
            self.finished.set()

    def start(self):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


def publish(host: str, port: int, username: str, password: str, index: int) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-publisher-{index}")
    client.username_pw_set(username, password)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    info = client.publish(
        f"sensores/{username}/system-test/{index}",
        payload=f'{{"iot":{index},"status":"ok"}}',
        qos=1,
    )
    info.wait_for_publish(timeout=10)
    if not info.is_published() or info.rc != mqtt.MQTT_ERR_SUCCESS:
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(f"publisher {index} failed: {info.rc}")
    client.loop_stop()
    client.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--users", type=Path, default=Path("users/users.txt"))
    args = parser.parse_args()

    (user1, pass1), (user2, pass2) = load_users(args.users)
    receivers = [
        Receiver(args.host, args.port, user1, pass1, expected=5),
        Receiver(args.host, args.port, user2, pass2, expected=5),
    ]

    try:
        for receiver in receivers:
            receiver.start()
        if not all(receiver.connected.wait(10) for receiver in receivers):
            errors = "; ".join(receiver.error or receiver.username for receiver in receivers)
            raise RuntimeError(f"receivers did not connect or subscribe: {errors}")

        time.sleep(1)
        for index in range(10):
            username, password = (user1, pass1) if index % 2 == 0 else (user2, pass2)
            publish(args.host, args.port, username, password, index)

        if not all(receiver.finished.wait(10) for receiver in receivers):
            raise RuntimeError("timeout waiting for subscriber messages")
        for receiver in receivers:
            if len(receiver.messages) != receiver.expected:
                raise RuntimeError(
                    f"{receiver.username}: received {len(receiver.messages)}, "
                    f"expected {receiver.expected}"
                )
            print(f"PASS {receiver.username}: {len(receiver.messages)} messages received")
        print("PASS: 10 publishers simulated, 2 subscribers validated")
        return 0
    finally:
        for receiver in receivers:
            receiver.stop()


if __name__ == "__main__":
    raise SystemExit(main())
