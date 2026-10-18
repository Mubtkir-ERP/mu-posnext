/**
 * Generate a UUID with fallback for environments that don't support crypto.randomUUID
 * @returns {string} - A unique identifier
 */
export function generateUUID() {
	if (globalThis.crypto?.randomUUID) {
		try {
			return globalThis.crypto.randomUUID();
		} catch (e) {
			// fallback below
		}
	}

	// Fallback for older WebViews/browsers without crypto.randomUUID().
	return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
		const r = (Math.random() * 16) | 0;
		const v = c === 'x' ? r : (r & 0x3) | 0x8;
		return v.toString(16);
	});
}
