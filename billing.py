"""Stripe billing helpers."""
import os
import stripe

FREE_MONTHLY_LIMIT = 3

PLANS = {
    "pro":  {"name": "Pro",  "amount": 1200, "label": "$12/mo"},
    "team": {"name": "Team", "amount": 3900, "label": "$39/mo"},
}


def _s():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


def get_price_id(plan: str) -> str:
    """Get or create a Stripe price ID for a given plan."""
    env_key = f"STRIPE_PRICE_ID_{plan.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]

    s = _s()
    cfg = PLANS[plan]
    product_name = f"Job Description Generator — {cfg['name']}"

    products = s.Product.list(limit=100)
    product = next((p for p in products.data if p.name == product_name and p.active), None)
    if not product:
        product = s.Product.create(name=product_name)

    prices = s.Price.list(product=product.id, limit=100)
    price = next(
        (p for p in prices.data
         if p.active and p.unit_amount == cfg["amount"]
         and p.recurring and p.recurring.interval == "month"),
        None,
    )
    if not price:
        price = s.Price.create(
            product=product.id,
            unit_amount=cfg["amount"],
            currency="usd",
            recurring={"interval": "month"},
        )
    return price.id


def create_checkout_session(plan: str, user_id: int, email: str, base_url: str) -> str:
    """Create a Stripe Checkout session and return the URL."""
    s = _s()
    session = s.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": get_price_id(plan), "quantity": 1}],
        customer_email=email,
        success_url=f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/?cancelled=1",
        metadata={"user_id": str(user_id), "plan": plan},
        allow_promotion_codes=True,
    )
    return session.url


def create_portal_session(customer_id: str, base_url: str) -> str:
    """Create a Stripe Customer Portal session and return the URL."""
    s = _s()
    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=base_url,
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict | None:
    """
    Verify and parse a Stripe webhook event.
    Returns {"user_id": int, "plan": str, "customer_id": str} on subscription change,
    or None if the event doesn't require a DB update.
    """
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = _s().Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        return None

    if event["type"] in ("checkout.session.completed",):
        obj = event["data"]["object"]
        if obj.get("mode") == "subscription":
            return {
                "user_id": int(obj["metadata"]["user_id"]),
                "plan": obj["metadata"]["plan"],
                "customer_id": obj["customer"],
                "subscription_id": obj["subscription"],
            }

    if event["type"] in ("customer.subscription.deleted",):
        sub = event["data"]["object"]
        # Look up user by customer ID — handled in main.py
        return {
            "customer_id": sub["customer"],
            "plan": "free",
            "subscription_id": sub["id"],
        }

    return None
