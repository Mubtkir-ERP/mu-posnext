const TERMINAL_KEY_PREFIX = "posnext_terminal_id_v1";

function clean(value) {
	return String(value || "").trim();
}

function slug(value) {
	return clean(value)
		.toUpperCase()
		.replace(/[^A-Z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 24) || "POS";
}

function randomSuffix() {
	try {
		if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().slice(0, 6).toUpperCase();
	} catch (_) {}
	return Math.random().toString(36).slice(2, 8).toUpperCase();
}

export function terminalStorageKey(posProfile = "") {
	return `${TERMINAL_KEY_PREFIX}:${clean(posProfile) || "default"}`;
}

export function getBrowserTerminalId(posProfile = "") {
	try {
		return clean(localStorage.getItem(terminalStorageKey(posProfile)));
	} catch (_) {
		return "";
	}
}

export function saveBrowserTerminalId(posProfile = "", terminalId = "") {
	const id = clean(terminalId);
	if (!id) return "";
	try {
		localStorage.setItem(terminalStorageKey(posProfile), id);
	} catch (_) {}
	return id;
}

export function ensureBrowserTerminalId(posProfile = "") {
	const existing = getBrowserTerminalId(posProfile);
	if (existing) return existing;
	return saveBrowserTerminalId(posProfile, `${slug(posProfile)}-${randomSuffix()}`);
}

export async function resolveTerminalIdentity(posProfile = "", { preferAgent = true } = {}) {
	try {
		const { getPrintTerminalId } = await import("@/utils/printProvider").catch(() => ({}));
		if (typeof getPrintTerminalId === "function") {
			const configuredTerminalId = clean(getPrintTerminalId());
			if (configuredTerminalId) {
				return { terminalId: configuredTerminalId, source: "terminal-setup", agent: null };
			}
		}
	} catch (_) {}

	return {
		terminalId: ensureBrowserTerminalId(posProfile),
		source: "browser-generated",
		agent: null,
	};
}
