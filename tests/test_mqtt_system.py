#!/usr/bin/env python3
"""Integration tests for 10 MQTT publishers and 2 subscribers."""

import os
import threading
import time
import unittest
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
    return users


class Receiver:
    def __init__(self, host: str, port: int, username: str, password: str, expected: int):
        self.username = username
        self.expected = expected
        self.messages: list[str] = []
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.finished = threading.Event()
        self.error = None
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"unittest-receiver-{username}",
        )
        self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.host = host
        self.port = port

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.error = f"connection failed: {reason_code}"
            return
        result, _ = client.subscribe(f"sensores/{self.username}/#", qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.error = f"subscribe request failed: {result}"
            return
        self.connected.set()

    def on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        if not granted_qos or granted_qos[0] >= 128:
            self.error = f"subscription rejected: {granted_qos}"
            return
        self.subscribed.set()

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
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"unittest-publisher-{index}",
    )
    client.username_pw_set(username, password)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    info = client.publish(
        f"sensores/{username}/unittest/{index}",
        payload=f'{{"iot":{index},"status":"ok"}}',
        qos=1,
    )
    info.wait_for_publish(timeout=10)
    try:
        if not info.is_published() or info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"publish failed: {info.rc}")
    finally:
        client.loop_stop()
        client.disconnect()


class MosquittoSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = os.getenv("MQTT_TEST_HOST", "127.0.0.1")
        cls.port = int(os.getenv("MQTT_TEST_PORT", "1883"))
        users_file = Path(os.getenv("MQTT_USERS_FILE", "users/users.txt"))
        cls.users = load_users(users_file)

    def test_users_file_has_two_iots(self):
        """The local credentials file contains both simulated IoT accounts."""
        self.assertGreaterEqual(len(self.users), 2)
        self.assertTrue(self.users[0][0].startswith("iot-"))
        self.assertTrue(self.users[1][0].startswith("iot-"))

    def run_load_test(self, publisher_count: int):
        """Run one load level with half the messages going to each subscriber."""
        (user1, pass1), (user2, pass2) = self.users[:2]
        expected_per_receiver = publisher_count // 2
        receivers = [
            Receiver(self.host, self.port, user1, pass1, expected=expected_per_receiver),
            Receiver(self.host, self.port, user2, pass2, expected=expected_per_receiver),
        ]
        try:
            for receiver in receivers:
                receiver.start()
            for receiver in receivers:
                self.assertTrue(receiver.connected.wait(10), receiver.error)
                self.assertTrue(receiver.subscribed.wait(10), receiver.error)

            time.sleep(1)
            for index in range(publisher_count):
                username, password = (user1, pass1) if index % 2 == 0 else (user2, pass2)
                publish(self.host, self.port, username, password, index)

            deadline = time.monotonic() + 10
            for receiver in receivers:
                remaining = max(0, deadline - time.monotonic())
                self.assertTrue(receiver.finished.wait(remaining), receiver.error)
                self.assertEqual(len(receiver.messages), receiver.expected, receiver.username)
        finally:
            for receiver in receivers:
                receiver.stop()

    def test_10_publishers_reach_two_subscribers(self):
        self.run_load_test(10)

    def test_20_publishers_reach_two_subscribers(self):
        self.run_load_test(20)

    def test_30_publishers_reach_two_subscribers(self):
        self.run_load_test(30)

    def test_40_publishers_reach_two_subscribers(self):
        self.run_load_test(40)

    def test_50_publishers_reach_two_subscribers(self):
        self.run_load_test(50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
