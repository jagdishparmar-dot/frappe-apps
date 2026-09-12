"""Print helpers for Desk print formats (challan number, INR words)."""

from __future__ import annotations

from frappe.utils import flt, getdate, nowdate


def challan_number(invoice) -> str:
    year = "2026"
    if getattr(invoice, "invoice_date", None):
        year = str(getdate(invoice.invoice_date).year)
    raw = str(getattr(invoice, "name", "") or "")
    suffix = (raw[-5:] if len(raw) > 5 else raw).upper().zfill(5)
    return f"CH-{year}-{suffix}"


def amount_in_words_inr(amount) -> str:
    num = int(round(abs(flt(amount))))
    if num == 0:
        return "Zero Rupees Only"

    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def hundreds(n: int) -> str:
        parts = []
        if n >= 100:
            parts.append(ones[n // 100] + " Hundred")
            n %= 100
            if n:
                parts.append("and")
        if n >= 20:
            word = tens[n // 10]
            if n % 10:
                word += "-" + ones[n % 10]
            parts.append(word)
        elif n:
            parts.append(ones[n])
        return " ".join(parts)

    crore, rem = divmod(num, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rem = divmod(rem, 1000)
    chunks = []
    if crore:
        chunks.append(hundreds(crore) + " Crore")
    if lakh:
        chunks.append(hundreds(lakh) + " Lakh")
    if thousand:
        chunks.append(hundreds(thousand) + " Thousand")
    if rem:
        chunks.append(hundreds(rem))
    return " ".join(chunks).strip() + " Rupees Only"


def today_iso() -> str:
    return str(nowdate())
