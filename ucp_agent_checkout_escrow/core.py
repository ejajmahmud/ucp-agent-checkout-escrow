"""Core Universal Commerce Protocol (UCP) checkout escrow state machine."""
import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


class EscrowError(Exception):
    """Raised on invalid UCP escrow state transition or policy violation."""


@dataclass
class CheckoutIntent:
    intent_id: str
    merchant_id: str
    items: List[Dict[str, Any]]
    total_cents: int
    currency: str
    status: str = "PENDING_APPROVAL"
    created_at: float = field(default_factory=time.time)
    idempotency_key: str = ""
    receipt_hash: str = ""


class UCPCheckoutEscrow:
    """Enforces spend caps, idempotency, and signed human approval for UCP checkouts."""

    def __init__(self, spend_cap_cents: int, secret: str, ttl_seconds: int = 300):
        self.spend_cap_cents = spend_cap_cents
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self._intents: Dict[str, CheckoutIntent] = {}
        self._idempotency_index: Dict[str, str] = {}

    def create_intent(
        self,
        intent_id: str,
        merchant_id: str,
        items: List[Dict[str, Any]],
        currency: str = "USD",
        idempotency_key: str = "",
    ) -> CheckoutIntent:
        if idempotency_key and idempotency_key in self._idempotency_index:
            return self._intents[self._idempotency_index[idempotency_key]]
        if not items:
            raise EscrowError("Cart must contain at least one item")

        total = sum(int(i["qty"]) * int(i["unit_cents"]) for i in items)
        if total <= 0:
            raise EscrowError("Checkout total must be positive")
        if total > self.spend_cap_cents:
            raise EscrowError(f"Total {total} cents exceeds cap {self.spend_cap_cents} cents")

        intent = CheckoutIntent(
            intent_id=intent_id,
            merchant_id=merchant_id,
            items=list(items),
            total_cents=total,
            currency=currency,
            idempotency_key=idempotency_key or intent_id,
        )
        self._intents[intent_id] = intent
        self._idempotency_index[intent.idempotency_key] = intent_id
        return intent

    def approve(self, intent_id: str, approver: str) -> str:
        intent = self._intents.get(intent_id)
        if not intent:
            raise EscrowError(f"Unknown intent {intent_id}")
        if intent.status == "COMMITTED":
            raise EscrowError("Intent already committed")
        if time.time() - intent.created_at > self.ttl_seconds:
            intent.status = "EXPIRED"
            raise EscrowError("Intent expired before approval")

        msg = f"{intent.intent_id}:{intent.merchant_id}:{intent.total_cents}:{approver}".encode("utf-8")
        token = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        intent.status = "APPROVED"
        return f"{approver}:{token}"

    def commit(self, intent_id: str, approval_token: str) -> Dict[str, Any]:
        intent = self._intents.get(intent_id)
        if not intent:
            raise EscrowError(f"Unknown intent {intent_id}")
        if intent.status == "COMMITTED":
            return {"intent_id": intent.intent_id, "status": "COMMITTED", "total_cents": intent.total_cents, "receipt_hash": intent.receipt_hash}
        if intent.status != "APPROVED":
            raise EscrowError(f"Cannot commit intent in state {intent.status}")
        if ":" not in approval_token:
            raise EscrowError("Malformed approval token")

        approver, sig = approval_token.split(":", 1)
        expected = hmac.new(
            self._secret,
            f"{intent.intent_id}:{intent.merchant_id}:{intent.total_cents}:{approver}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise EscrowError("Invalid approval signature")

        intent.status = "COMMITTED"
        intent.receipt_hash = hashlib.sha256(f"{intent.idempotency_key}:{sig}".encode("utf-8")).hexdigest()[:16]
        return {
            "intent_id": intent.intent_id,
            "merchant_id": intent.merchant_id,
            "status": intent.status,
            "total_cents": intent.total_cents,
            "currency": intent.currency,
            "receipt_hash": intent.receipt_hash,
        }
