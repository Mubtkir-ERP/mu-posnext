/**
 * Persistent client request IDs for retry-safe POS mutations.
 * The payload fingerprint keeps a corrected/new operation from accidentally
 * reusing the ID of an older failed operation.
 */
function stableStringify(value) {
	if (value === null || typeof value !== "object") return JSON.stringify(value)
	if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`
	return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`
}

function hashString(value) {
	let hash = 2166136261
	for (let i = 0; i < value.length; i++) {
		hash ^= value.charCodeAt(i)
		hash = Math.imul(hash, 16777619)
	}
	return (hash >>> 0).toString(36)
}

function newRequestId() {
	if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
	return `req-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

export function getPersistentRequestId(namespace, identity, payload = null) {
	const fingerprint = hashString(stableStringify(payload))
	const key = `pos_next_request:${namespace}:${identity}:${fingerprint}`
	let requestId = localStorage.getItem(key)
	if (!requestId) {
		requestId = newRequestId()
		localStorage.setItem(key, requestId)
	}
	return { requestId, key }
}

export function clearPersistentRequestId(key, requestId = null) {
	if (!key) return
	if (requestId && localStorage.getItem(key) !== requestId) return
	localStorage.removeItem(key)
}
