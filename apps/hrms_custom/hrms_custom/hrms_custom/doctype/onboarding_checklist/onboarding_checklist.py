from frappe.model.document import Document


class OnboardingChecklist(Document):
	def validate(self):
		self.status = compute_status([task.status for task in self.tasks])


def compute_status(task_statuses: list[str]) -> str:
	done = sum(1 for status in task_statuses if status == "Done")
	if task_statuses and done == len(task_statuses):
		return "Completed"
	return "In Progress" if done else "Not Started"
