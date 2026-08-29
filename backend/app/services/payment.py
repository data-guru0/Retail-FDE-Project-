"""Mock payment. Luhn-validates a fake card number. No money moves, nothing stored
beyond the last 4 digits on the order.
"""
from __future__ import annotations

from fastapi import HTTPException


def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 12:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def charge(card_number: str, exp: str, cvc: str) -> str:
    """Returns the last 4 digits on 'success'. Raises 402 on an invalid card."""
    clean = card_number.replace(" ", "").replace("-", "")
    if not luhn_ok(clean):
        raise HTTPException(402, "card declined (failed Luhn check)")
    if not (len(cvc) in (3, 4) and cvc.isdigit()):
        raise HTTPException(402, "invalid CVC")
    return clean[-4:]


if __name__ == "__main__":
    assert luhn_ok("4242424242424242")
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4242424242424241")
    assert not luhn_ok("1234")
    print("payment self-check ok")
