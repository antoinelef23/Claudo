from webhooks.model import DELIVERED, DEAD_LETTER, Delivery, backoff_ms
from webhooks.signing import sign


def deliver(
    store,
    transport,
    subscription,
    event,
    clock,
    base_ms: int = 1000,
    cap_ms: int = 60000,
) -> Delivery:
    delivery = store.enqueue(subscription.id, event.id)

    if delivery.state in {DELIVERED, DEAD_LETTER}:
        return delivery

    for n in range(1, subscription.max_attempts + 1):
        sig = sign(subscription.secret, event.payload)
        ok = transport.send(subscription.url, event.payload, sig)
        delivery.attempts += 1
        if ok:
            delivery.state = DELIVERED
            return delivery
        delivery.next_at = clock() + backoff_ms(n, base_ms, cap_ms)
        delivery.last_error = f"attempt {n} failed"

    delivery.state = DEAD_LETTER
    return delivery
