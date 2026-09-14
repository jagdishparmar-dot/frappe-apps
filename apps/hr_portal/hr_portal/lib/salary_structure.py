from __future__ import annotations

SALARY_AMOUNT_FIELDS = (
	"basic",
	"hra",
	"special_allowance",
	"other_earnings",
	"deductions",
)

SalaryAmounts = dict[str, float]


def zero_salary_amounts() -> SalaryAmounts:
	return {key: 0.0 for key in SALARY_AMOUNT_FIELDS}


def build_salary_components(amounts: SalaryAmounts) -> list[dict]:
	return [
		{"component_key": "basic", "label": "Basic", "amount": float(amounts.get("basic") or 0), "component_type": "earning"},
		{"component_key": "hra", "label": "HRA", "amount": float(amounts.get("hra") or 0), "component_type": "earning"},
		{
			"component_key": "special_allowance",
			"label": "Special Allowance",
			"amount": float(amounts.get("special_allowance") or 0),
			"component_type": "earning",
		},
		{
			"component_key": "other_earnings",
			"label": "Other Earnings",
			"amount": float(amounts.get("other_earnings") or 0),
			"component_type": "earning",
		},
		{
			"component_key": "deductions",
			"label": "Deductions",
			"amount": float(amounts.get("deductions") or 0),
			"component_type": "deduction",
		},
	]


def compute_ctc_monthly(amounts: SalaryAmounts) -> float:
	return (
		float(amounts.get("basic") or 0)
		+ float(amounts.get("hra") or 0)
		+ float(amounts.get("special_allowance") or 0)
		+ float(amounts.get("other_earnings") or 0)
		- float(amounts.get("deductions") or 0)
	)


def salary_amounts_from_components(components: list[dict] | None) -> SalaryAmounts:
	amounts = zero_salary_amounts()
	for row in components or []:
		key = row.get("component_key") or row.get("key")
		if key in amounts:
			amounts[key] = float(row.get("amount") or 0)
	return amounts


def normalize_amounts_payload(payload: dict) -> SalaryAmounts:
	"""Accept camelCase (mobile/legacy) or snake_case keys."""
	mapping = {
		"basic": "basic",
		"hra": "hra",
		"specialAllowance": "special_allowance",
		"special_allowance": "special_allowance",
		"otherEarnings": "other_earnings",
		"other_earnings": "other_earnings",
		"deductions": "deductions",
	}
	amounts = zero_salary_amounts()
	for source, target in mapping.items():
		if source in payload and payload[source] is not None:
			amounts[target] = max(0.0, float(payload[source] or 0))
	return amounts
