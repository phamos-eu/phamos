// frappe-ui's realtime socket goes to port 9000 unless it gets a port. A site served on a port,
// such as a local bench on 8003 with socket.io on 9003, then gets no realtime. The boot carries the
// bench's socketio_port (phamos/www/spa_boot.py). Behind a proxy the URL has no port and frappe-ui
// ignores this one.

/**
 * frappe-ui's `socketio` plugin options for this site.
 *
 * @param {{ socketio_port?: number } | undefined} boot - `window.frappe.boot`
 * @returns {{ port: number | undefined }}
 */
export function socketioOptions(boot) {
	return { port: boot?.socketio_port }
}
