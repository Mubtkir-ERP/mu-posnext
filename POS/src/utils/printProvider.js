/**
 * Print Provider & Terminal ID resolver
 */

const TERMINAL_STORAGE_KEY = "pos_print_terminal_id";

export function getPrintTerminalId() {
	try {
		return localStorage.getItem(TERMINAL_STORAGE_KEY) || "";
	} catch (_) {
		return "";
	}
}

export function setPrintTerminalId(id) {
	try {
		if (id) {
			localStorage.setItem(TERMINAL_STORAGE_KEY, String(id).trim());
		} else {
			localStorage.removeItem(TERMINAL_STORAGE_KEY);
		}
	} catch (_) {}
}

export default {
	getPrintTerminalId,
	setPrintTerminalId,
};
