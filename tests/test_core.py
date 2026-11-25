"""Tests for UCP Agent Checkout Escrow."""
import unittest
from ucp_agent_checkout_escrow.core import UCPCheckoutEscrow, EscrowError


class TestUCPCheckoutEscrow(unittest.TestCase):
    def setUp(self):
        self.escrow = UCPCheckoutEscrow(spend_cap_cents=5000, secret="s3cr3t")

    def test_full_approve_and_idempotent_commit(self):
        intent = self.escrow.create_intent("i1", "m1", [{"sku": "A", "qty": 2, "unit_cents": 1000}], idempotency_key="idem-1")
        same = self.escrow.create_intent("i2", "m1", [{"sku": "A", "qty": 2, "unit_cents": 1000}], idempotency_key="idem-1")
        self.assertEqual(intent.intent_id, same.intent_id)
        tok = self.escrow.approve("i1", "alice")
        r1 = self.escrow.commit("i1", tok)
        r2 = self.escrow.commit("i1", tok)
        self.assertEqual(r1["receipt_hash"], r2["receipt_hash"])
        self.assertEqual(r1["total_cents"], 2000)

    def test_spend_cap_enforced(self):
        with self.assertRaises(EscrowError):
            self.escrow.create_intent("i-over", "m1", [{"sku": "X", "qty": 1, "unit_cents": 9999}])

    def test_rejects_forged_signature(self):
        self.escrow.create_intent("i-bad", "m1", [{"sku": "B", "qty": 1, "unit_cents": 500}])
        self.escrow.approve("i-bad", "alice")
        with self.assertRaises(EscrowError):
            self.escrow.commit("i-bad", "alice:deadbeef")

    def test_commit_without_approval_fails(self):
        self.escrow.create_intent("i-unapp", "m1", [{"sku": "C", "qty": 1, "unit_cents": 500}])
        with self.assertRaises(EscrowError):
            self.escrow.commit("i-unapp", "alice:1234")
