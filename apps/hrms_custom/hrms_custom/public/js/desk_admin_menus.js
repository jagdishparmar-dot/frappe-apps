(() => {
	const boot = (window.frappe && frappe.boot) || {};

	function isAdmin() {
		return !!boot.hrms_administrator_desk;
	}

	function restrictedNames() {
		return new Set(boot.hrms_admin_only_menu_names || ["edit-sidebar", "help"]);
	}

	function restrictedLabels() {
		return new Set(
			boot.hrms_admin_only_menu_labels || ["Edit Sidebar", "Help", "About", "Frappe Support"]
		);
	}

	function isRestricted(item) {
		if (!item) {
			return false;
		}
		if (item.name && restrictedNames().has(item.name)) {
			return true;
		}
		const label = item.label || item.item_label;
		if (label && restrictedLabels().has(label)) {
			return true;
		}
		if (typeof item.action === "string" && item.action.includes("show_about")) {
			return true;
		}
		const target = String(item.route || item.url || "");
		if (target.includes("frappe.io/support") || target.includes("support.frappe")) {
			return true;
		}
		if (
			typeof item.onClick === "function" &&
			/show_about|support\.frappe/.test(String(item.onClick))
		) {
			return true;
		}
		return false;
	}

	function filterMenuItems(items) {
		if (!Array.isArray(items)) {
			return items;
		}
		const filtered = [];
		for (const item of items) {
			if (item && item.is_divider && typeof item.condition === "function") {
				continue;
			}
			if (isRestricted(item)) {
				continue;
			}
			if (item && Array.isArray(item.items)) {
				const nested = filterMenuItems(item.items);
				if (!nested.length && (item.name === "help" || item.label === "Help")) {
					continue;
				}
				filtered.push(Object.assign({}, item, { items: nested }));
				continue;
			}
			filtered.push(item);
		}
		return filtered;
	}

	if (!isAdmin() && boot.navbar_settings) {
		boot.navbar_settings.help_dropdown = [];
	}

	if (frappe.ui && typeof frappe.ui.create_menu === "function" && !frappe.ui.create_menu.__hrms_admin_menus) {
		const originalCreateMenu = frappe.ui.create_menu;
		frappe.ui.create_menu = function (opts) {
			if (!isAdmin() && opts && Array.isArray(opts.menu_items)) {
				opts.menu_items = filterMenuItems(opts.menu_items);
			}
			return originalCreateMenu.apply(this, arguments);
		};
		frappe.ui.create_menu.__hrms_admin_menus = true;
	}

	if (
		frappe.ui &&
		frappe.ui.SidebarHeader &&
		frappe.ui.SidebarHeader.prototype.setup_app_switcher &&
		!frappe.ui.SidebarHeader.prototype.setup_app_switcher.__hrms_admin_menus
	) {
		const originalSwitcher = frappe.ui.SidebarHeader.prototype.setup_app_switcher;
		frappe.ui.SidebarHeader.prototype.setup_app_switcher = function () {
			if (!isAdmin()) {
				this.dropdown_items = filterMenuItems(this.dropdown_items);
			}
			return originalSwitcher.apply(this, arguments);
		};
		frappe.ui.SidebarHeader.prototype.setup_app_switcher.__hrms_admin_menus = true;
	}

	if (
		frappe.ui &&
		frappe.ui.toolbar &&
		typeof frappe.ui.toolbar.show_about === "function" &&
		!frappe.ui.toolbar.show_about.__hrms_admin_menus
	) {
		const originalAbout = frappe.ui.toolbar.show_about;
		frappe.ui.toolbar.show_about = function () {
			if (!isAdmin()) {
				return;
			}
			return originalAbout.apply(this, arguments);
		};
		frappe.ui.toolbar.show_about.__hrms_admin_menus = true;
	}
})();
