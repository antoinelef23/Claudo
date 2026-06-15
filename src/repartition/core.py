def split(total: int, parts: int) -> list[int]:
    if parts <= 0 or total < 0:
        raise ValueError(
            f"total must be >= 0 and parts must be > 0, got total={total}, parts={parts}"
        )
    base, r = divmod(total, parts)
    return [base + 1] * r + [base] * (parts - r)
