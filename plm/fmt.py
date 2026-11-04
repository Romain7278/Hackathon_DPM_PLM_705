"""Mise en forme française des nombres."""

NBSP = " "
THIN = " "


def number(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", THIN).replace(".", ",")


def eur(value, decimals=0):
    return f"{number(value, decimals)}{NBSP}€"


def signed_eur(value, decimals=0):
    return f"{'+' if value > 0 else ''}{eur(value, decimals)}"


def compact_eur(value):
    size = abs(value)
    if size >= 1e6:
        return f"{number(value / 1e6, 2)}{NBSP}M€"
    if size >= 1e4:
        return f"{number(value / 1e3, 0)}{NBSP}k€"
    return eur(value)


def signed_compact_eur(value):
    return f"{'+' if value > 0 else ''}{compact_eur(value)}"


def kg(value):
    text = f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text}{NBSP}kg"


def signed_kg(value):
    return f"{'+' if value > 0 else ''}{kg(round(value, 2))}"


def pct(fraction, decimals=0):
    return f"{number(fraction * 100, decimals)}{NBSP}%"
