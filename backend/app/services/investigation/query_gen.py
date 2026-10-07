def generate_queries(brand: str, product: str | None, aspect: str) -> list[str]:
    subject = f"{brand} {product}" if product else brand
    return [
        f"{subject} {aspect} problem",
        f"{subject} {aspect} issue",
        f"{brand} {aspect} update",
    ][:3]
