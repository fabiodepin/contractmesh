"""Tests for ExampleService (test anchor for ContractMesh index smoke)."""

import unittest

from example import ExampleService


class TestExampleService(unittest.TestCase):
    def test_greet_returns_message(self) -> None:
        service = ExampleService()
        self.assertEqual(service.greet("world"), "Hello, world")

    def test_greet_rejects_empty_name(self) -> None:
        service = ExampleService()
        with self.assertRaises(ValueError):
            service.greet("")
