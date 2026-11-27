// Idea Catcher (phamos/phamos#2200): catch an idea in one step, link it afterwards.
// Plain script, no build step. Server side: phamos/api/idea_catcher.py.
;(function () {
	"use strict"

	var boot = window.idea_boot || {}
	var messages = boot.__messages || {}
	var API = "/api/method/phamos.api.idea_catcher."
	var QUEUE_KEY = "phamos_idea_queue:" + boot.user

	function __(text, args) {
		var out = messages[text] || text
		;(args || []).forEach(function (value, i) {
			out = out.split("{" + i + "}").join(value)
		})
		return out
	}

	var $ = function (id) {
		return document.getElementById(id)
	}
	var text = $("text")
	var saveBtn = $("save")
	var sheet = $("sheet")
	var scrim = $("scrim")
	var search = $("search")
	var list = $("list")
	var choose = $("choose")
	var queueBadge = $("queue")

	document.querySelectorAll("[data-t]").forEach(function (el) {
		el.textContent = __(el.getAttribute("data-t"))
	})
	text.placeholder = __("What's the idea?")
	search.placeholder = __("Search my ideas")

	// --- server ---------------------------------------------------------------------------

	function call(method, args, post) {
		var url = API + method
		var options = { headers: { Accept: "application/json" }, credentials: "same-origin" }
		if (post) {
			options.method = "POST"
			options.headers["Content-Type"] = "application/json"
			options.headers["X-Frappe-CSRF-Token"] = window.csrf_token
			options.body = JSON.stringify(args || {})
		} else if (args) {
			url += "?" + new URLSearchParams(args).toString()
		}
		return fetch(url, options).then(function (response) {
			return response.json().then(
				function (body) {
					if (!response.ok) {
						var error = new Error(serverMessage(body) || response.statusText)
						error.status = response.status
						error.excType = body.exc_type
						throw error
					}
					return body.message
				},
				function () {
					var error = new Error(response.statusText)
					error.status = response.status
					throw error
				}
			)
		})
	}

	function serverMessage(body) {
		try {
			var list = JSON.parse(body._server_messages || "[]")
			return list.length ? JSON.parse(list[0]).message : body.exception
		} catch (e) {
			return body && body.exception
		}
	}

	// --- offline queue (#2204) --------------------------------------------------------------
	// Every caught idea goes through the queue first, so nothing is lost when the phone is offline
	// or the request fails. The client id lets the server ignore a second send of the same idea.

	function readQueue() {
		try {
			return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]")
		} catch (e) {
			return []
		}
	}

	function writeQueue(queue) {
		try {
			localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
		} catch (e) {
			/* private mode: the idea is still sent right away */
		}
		renderQueue(queue)
	}

	var needsLogin = false

	function renderQueue(queue) {
		queueBadge.hidden = !queue.length
		if (needsLogin) {
			queueBadge.textContent = __("Sign in to send {0}", [queue.length])
			return
		}
		queueBadge.textContent =
			queue.length === 1 ? __("1 idea waiting to send") : __("{0} ideas waiting to send", [queue.length])
	}

	function newClientId() {
		if (window.crypto && crypto.randomUUID) return crypto.randomUUID()
		return Date.now().toString(36) + Math.random().toString(36).slice(2)
	}

	var flushing = null

	// Send what is queued, oldest first. Resolves with the ideas the server made, by client id.
	function flush() {
		if (flushing) return flushing
		flushing = (async function () {
			var made = {}
			var queue = readQueue()
			while (queue.length) {
				var item = queue[0]
				try {
					made[item.client_id] = await call("save_idea", { text: item.text, client_id: item.client_id }, true)
					needsLogin = false
				} catch (error) {
					// No connection or server down: keep it and try later. A refusal (4xx) will not get
					// better by retrying, so the text goes back into the box instead of looping.
					// Signed out (401/403) or a stale CSRF token (400 CSRFTokenError): keep everything;
					// the badge offers the login, which also loads a fresh token.
					if (
						error.status === 401 ||
						error.status === 403 ||
						(error.status === 400 && error.excType === "CSRFTokenError")
					) {
						needsLogin = true
						renderQueue(queue)
						break
					}
					// Any other 4xx except timeout (408) and rate limit (429) is refused for good
					// (validation, too large, unknown method): out of the queue so it cannot block the
					// ideas behind it, and the text goes back into the box after anything typed there.
					if (error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) {
						queue.shift()
						writeQueue(queue)
						text.value = text.value.trim() ? text.value + "\n\n" + item.text : item.text
						updateSave()
						toast(error.message)
						continue
					}
					// Offline, timeout, rate limit, server error: try again later.
					break
				}
				queue = readQueue().filter(function (q) {
					return q.client_id !== item.client_id
				})
				writeQueue(queue)
			}
			return made
		})().finally(function () {
			flushing = null
		})
		return flushing
	}

	window.addEventListener("online", flush)
	document.addEventListener("visibilitychange", function () {
		if (!document.hidden) flush()
	})

	// --- capture (#2201) ------------------------------------------------------------------

	function updateSave() {
		saveBtn.disabled = !text.value.trim()
	}
	text.addEventListener("input", updateSave)

	saveBtn.addEventListener("click", async function () {
		var value = text.value.trim()
		if (!value) return
		var clientId = newClientId()
		var queue = readQueue()
		queue.push({ client_id: clientId, text: value, created: new Date().toISOString() })
		writeQueue(queue)
		text.value = ""
		updateSave()
		text.blur()
		saveBtn.disabled = true
		var made = await flush()
		var idea = made[clientId]
		if (idea) {
			openSheet(idea)
		} else {
			toast(__("Kept on this phone. It is sent when you are online again."))
			focusText()
		}
	})

	function focusText() {
		setTimeout(function () {
			text.focus()
		}, 50)
	}

	// --- link after save (#2203, #2206) ---------------------------------------------------------

	var current = null // the idea just caught
	var chosen = null // the idea it is linked to
	var searchTimer = null

	function openSheet(idea) {
		current = idea
		chosen = null
		choose.hidden = true
		search.value = ""
		$("suggest").hidden = true
		sheet.hidden = false
		scrim.hidden = false
		requestAnimationFrame(function () {
			sheet.classList.add("open")
			scrim.classList.add("open")
		})
		loadList()
		if (boot.ai_suggestions) loadSuggestions()
		// With a mouse and keyboard, go on typing in the search; on a phone that would only raise
		// the keyboard over the list.
		if (!window.matchMedia("(pointer: coarse)").matches) search.focus()
	}

	function closeSheet(message) {
		sheet.classList.remove("open")
		scrim.classList.remove("open")
		setTimeout(function () {
			sheet.hidden = true
			scrim.hidden = true
		}, 250)
		current = null
		if (message) toast(message)
		focusText()
	}

	function row(idea, band) {
		var li = document.createElement("li")
		li.className = "item"
		var title = document.createElement("div")
		title.className = "item-title"
		title.textContent = idea.title
		li.appendChild(title)
		if (idea.summary && idea.summary !== idea.title) {
			var summary = document.createElement("div")
			summary.className = "item-sub"
			summary.textContent = idea.summary
			li.appendChild(summary)
		}
		if (band) {
			var chip = document.createElement("span")
			chip.className = "chip chip-" + band.replace(" ", "-")
			chip.textContent = __(band.charAt(0).toUpperCase() + band.slice(1))
			li.appendChild(chip)
		}
		li.tabIndex = 0
		li.setAttribute("role", "button")
		li.addEventListener("click", function () {
			pick(idea, li)
		})
		li.addEventListener("keydown", function (event) {
			if (event.key === "Enter" || event.key === " ") {
				event.preventDefault()
				pick(idea, li)
				$("spawned").focus()
			}
		})
		return li
	}

	function fill(ul, ideas, withBand, emptyText) {
		ul.innerHTML = ""
		ideas.forEach(function (idea) {
			ul.appendChild(row(idea, withBand ? idea.band : null))
		})
		if (!ideas.length && emptyText) {
			var li = document.createElement("li")
			li.className = "empty"
			li.textContent = emptyText
			ul.appendChild(li)
		}
	}

	function loadList() {
		var query = search.value.trim()
		call("search_my_ideas", { query: query, exclude: current ? current.name : "" })
			.then(function (ideas) {
				fill(list, ideas, false, query ? __("No idea matches.") : __("No other ideas yet."))
			})
			.catch(function (error) {
				fill(list, [], false, error.message)
			})
	}

	function loadSuggestions() {
		var box = $("suggest")
		var ul = $("suggest-list")
		fill(ul, [], false, __("Looking for close ideas …"))
		box.hidden = false
		call("suggest_ideas", { name: current.name })
			.then(function (result) {
				if (!result.enabled) {
					box.hidden = true
					return
				}
				fill(ul, result.ideas, true, result.error || __("Nothing close found."))
			})
			.catch(function () {
				box.hidden = true
			})
	}

	search.addEventListener("input", function () {
		clearTimeout(searchTimer)
		searchTimer = setTimeout(loadList, 250)
	})

	function pick(idea, li) {
		chosen = idea
		sheet.querySelectorAll(".item.selected").forEach(function (el) {
			el.classList.remove("selected")
		})
		li.classList.add("selected")
		$("choose-title").textContent = idea.title
		choose.hidden = false
	}

	function link(mode) {
		if (!current || !chosen) return
		var target = chosen
		call("link_idea", { name: current.name, target: target.name, mode: mode }, true)
			.then(function () {
				closeSheet(
					mode === "spawned"
						? __("Linked: grew out of {0}", [target.title])
						: __("Added to {0}", [target.title])
				)
			})
			.catch(function (error) {
				toast(error.message || __("No connection. The idea is saved; link it later in the Personal Cockpit."))
			})
	}

	$("spawned").addEventListener("click", function () {
		link("spawned")
	})
	$("append").addEventListener("click", function () {
		link("append")
	})
	$("skip").addEventListener("click", function () {
		closeSheet()
	})
	scrim.addEventListener("click", function () {
		closeSheet()
	})

	// --- toast ---------------------------------------------------------------------------

	var toastTimer = null
	function toast(message) {
		var el = $("toast")
		el.textContent = message
		el.hidden = false
		requestAnimationFrame(function () {
			el.classList.add("open")
		})
		clearTimeout(toastTimer)
		toastTimer = setTimeout(function () {
			el.classList.remove("open")
			setTimeout(function () {
				el.hidden = true
			}, 250)
		}, 3200)
	}

	// Keyboard (hardware keyboards, desktop): Cmd/Ctrl+Enter or Cmd/Ctrl+S saves, as cockpit dialogs
	// confirm with Cmd/Ctrl+S (#2032); Esc closes the link sheet.
	document.addEventListener("keydown", function (event) {
		var mod = event.metaKey || event.ctrlKey
		if (mod && (event.key === "Enter" || event.key === "s" || event.key === "S")) {
			event.preventDefault()
			if (sheet.hidden && !saveBtn.disabled) saveBtn.click()
		} else if (event.key === "Escape" && !sheet.hidden) {
			event.preventDefault()
			closeSheet()
		}
	})

	queueBadge.addEventListener("click", function () {
		// The queue stays in localStorage, so leaving for the login page loses nothing.
		if (needsLogin) window.location.href = "/login?redirect-to=/idea"
		else flush()
	})

	renderQueue(readQueue())
	updateSave()
	flush()
	focusText()
})()
