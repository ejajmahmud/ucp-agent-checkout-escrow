"""CLI for UCP Agent Checkout Escrow."""
import argparse
import json
from .core import UCPCheckoutEscrow


def main():
    parser = argparse.ArgumentParser(description="UCP Agent Checkout Escrow CLI")
    parser.add_argument("--cap", type=int, default=10000, help="Spend cap in cents")
    parser.add_argument("--demo", action="store_true", help="Run sample UCP escrow checkout")
    args = parser.parse_args()

    escrow = UCPCheckoutEscrow(spend_cap_cents=args.cap, secret="demo-secret")
    intent = escrow.create_intent("ord-demo", "cloud-store", [{"sku": "GPU-HR", "qty": 2, "unit_cents": 1200}])
    token = escrow.approve(intent.intent_id, approver="operator")
    print(json.dumps(escrow.commit(intent.intent_id, token), indent=2))


if __name__ == "__main__":
    main()
