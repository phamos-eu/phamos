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

	// --- keyboard (#2216) ---------------------------------------------------------------------
	// iOS Safari leaves the layout viewport (what position: fixed and 100dvh measure) behind the
	// on-screen keyboard. The visual viewport is what the user sees, so the page follows it: the
	// app takes its height and offset, the sheet and toast sit --kb above the layout bottom.
	// Android with interactive-widget=resizes-content shrinks both, so --kb stays 0 there.
	var root = document.documentElement
	function fitToKeyboard() {
		var vv = window.visualViewport
		if (!vv) return
		// Pinch-zoom shrinks the visual viewport too; that is no keyboard.
		var zoomed = vv.scale > 1.01
		var kb = zoomed ? 0 : Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
		root.style.setProperty("--vvh", vv.height + "px")
		root.style.setProperty("--vv-top", vv.offsetTop + "px")
		root.style.setProperty("--kb", kb + "px")
		// Keyboard up: a text field has the cursor, and iOS reports the keyboard as --kb while
		// Android shows a much shorter visible area. A short desktop window alone is not enough.
		var active = document.activeElement
		var typing = !!active && (/^(INPUT|TEXTAREA)$/.test(active.tagName) || active.isContentEditable)
		root.classList.toggle(
			"kb-open",
			!zoomed && typing && (kb > 80 || vv.height < window.screen.height * 0.6)
		)
	}
	if (window.visualViewport) {
		window.visualViewport.addEventListener("resize", fitToKeyboard)
		window.visualViewport.addEventListener("scroll", fitToKeyboard)
	}
	// The class follows the cursor: in on focus, out when the field is left.
	document.addEventListener("focusin", fitToKeyboard)
	document.addEventListener("focusout", function () {
		setTimeout(fitToKeyboard, 0)
	})
	fitToKeyboard()

	document.querySelectorAll("[data-t]").forEach(function (el) {
		el.textContent = __(el.getAttribute("data-t"))
	})
	text.placeholder = __("What's the idea?")
	search.placeholder = __("Search my ideas")

	// --- server ---------------------------------------------------------------------------

	function call(method, args, post) {
		// Short names are Idea Catcher methods; dotted paths reach other modules (the Personal
		// Cockpit's idea endpoints, #2210).
		var url = method.indexOf(".") > -1 ? "/api/method/" + method : API + method
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
			// Only on the Catch view, not while the link sheet is open or another field has the cursor.
			if (!sheet.hidden || currentView !== "catch") return
			var active = document.activeElement
			if (active && active !== text && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return
			text.focus({ preventScroll: true })
			// Put the cursor after any text already there (e.g. text put back from the queue).
			var end = text.value.length
			text.setSelectionRange(end, end)
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
			focusText()
		}, 250)
		current = null
		if (message) toast(message)
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
			.then(function (result) {
				if (mode === "spawned") {
					closeSheet(__("Linked: grew out of {0}", [target.title]))
					return
				}
				closeSheet()
				// Undo for a few seconds (#2209): puts both ideas back and opens the sheet again.
				toast(__("Added to {0}", [target.title]), {
					label: __("Undo"),
					duration: UNDO_MS,
					run: function () {
						call("undo_append", { token: result.undo }, true)
							.then(function (idea) {
								openSheet(idea)
							})
							.catch(function (error) {
								toast(error.message)
							})
					},
				})
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
	var UNDO_MS = 8000
	// A short message; with `action` ({label, run, duration}) it carries one button, e.g. Undo.
	function toast(message, action) {
		var el = $("toast")
		el.textContent = ""
		var text = document.createElement("span")
		text.textContent = message
		el.appendChild(text)
		if (action) {
			var button = document.createElement("button")
			button.className = "toast-action"
			button.textContent = action.label
			button.addEventListener("click", function () {
				hideToast()
				action.run()
			})
			el.appendChild(button)
		}
		el.classList.toggle("has-action", !!action)
		el.hidden = false
		requestAnimationFrame(function () {
			el.classList.add("open")
		})
		clearTimeout(toastTimer)
		toastTimer = setTimeout(hideToast, (action && action.duration) || 3200)
	}

	function hideToast() {
		var el = $("toast")
		clearTimeout(toastTimer)
		el.classList.remove("open")
		setTimeout(function () {
			if (!el.classList.contains("open")) el.hidden = true
		}, 250)
	}

	// Keyboard (hardware keyboards, desktop): Cmd/Ctrl+Enter or Cmd/Ctrl+S saves, as cockpit dialogs
	// confirm with Cmd/Ctrl+S (#2032); Esc closes the link sheet.
	document.addEventListener("keydown", function (event) {
		var mod = event.metaKey || event.ctrlKey
		if (mod && (event.key === "Enter" || event.key === "s" || event.key === "S")) {
			event.preventDefault()
			if (currentView === "detail") {
				if (!$("d-save").disabled) $("d-save").click()
			} else if (currentView === "catch" && sheet.hidden && !saveBtn.disabled) saveBtn.click()
		} else if (event.key === "Escape" && !sheet.hidden) {
			event.preventDefault()
			closeSheet()
		}
	})

	// --- install as an app (#2217) -------------------------------------------------------------
	// Chrome and Edge (desktop and Android) fire beforeinstallprompt when the page is installable
	// (manifest with icons, start_url, standalone). Keep the event and offer it on our own button.
	// iOS Safari has no such event, so it gets a one-time note about the share menu instead.

	var installBtn = $("install")
	var iosHint = $("ios-hint")
	var deferredInstall = null
	var IOS_HINT_KEY = "phamos_idea_ios_hint_dismissed"

	function runningAsApp() {
		return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true
	}

	window.addEventListener("beforeinstallprompt", function (event) {
		event.preventDefault()
		deferredInstall = event
		installBtn.hidden = runningAsApp()
	})

	installBtn.addEventListener("click", async function () {
		if (!deferredInstall) return
		// An install event can open its dialog only once. After "not now" Chrome fires a fresh
		// beforeinstallprompt, and the listener above shows the button again.
		var prompt = deferredInstall
		deferredInstall = null
		installBtn.hidden = true
		try {
			prompt.prompt()
			await prompt.userChoice
		} catch (e) {
			/* the browser refused or closed the dialog */
		}
		focusText()
	})

	window.addEventListener("appinstalled", function () {
		deferredInstall = null
		installBtn.hidden = true
	})

	function iosHintDismissed() {
		try {
			return localStorage.getItem(IOS_HINT_KEY) === "1"
		} catch (e) {
			return false
		}
	}

	if (root.getAttribute("data-platform") === "ios" && !runningAsApp() && !iosHintDismissed()) {
		iosHint.hidden = false
	}
	$("ios-hint-close").addEventListener("click", function () {
		iosHint.hidden = true
		try {
			localStorage.setItem(IOS_HINT_KEY, "1")
		} catch (e) {
			/* private mode: it shows again next time */
		}
		focusText()
	})

	// --- focus (#2217) --------------------------------------------------------------------------
	// The cursor waits in the box on open, on reload, and when the app comes back to the front.
	// Phones raise the keyboard only on a tap; the cursor is placed either way.
	window.addEventListener("pageshow", focusText)
	document.addEventListener("visibilitychange", function () {
		if (!document.hidden) focusText()
	})
	window.addEventListener("focus", focusText)

	queueBadge.addEventListener("click", function () {
		// The queue stays in localStorage, so leaving for the login page loses nothing.
		if (needsLogin) window.location.href = "/login?redirect-to=/idea"
		else flush()
	})


	// --- views: Catch, My ideas, one idea, Vote (#2210) ----------------------------------------
	// Hash routes, so the phone's back gesture and the browser's back button work:
	// #/ catch · #/ideas · #/idea/<name> · #/vote · #/vote/<name>
	// Reading, editing, growing and voting go to the Personal Cockpit's endpoints; only capture
	// works offline.

	var PC = "phamos.api.personal_cockpit."
	var currentView = "catch"
	var VIEWS = ["catch", "ideas", "detail", "vote", "vote-detail"]
	var TAB_OF = { catch: "catch", ideas: "ideas", detail: "ideas", vote: "vote", "vote-detail": "vote" }
	var options = null // stages and their jobs, loaded once
	var detail = null // the idea open on #/idea/<name>
	var backBtn = $("back")

	function showView(name, title) {
		currentView = name
		VIEWS.forEach(function (view) {
			$("view-" + view).hidden = view !== name
		})
		document.querySelectorAll(".tab").forEach(function (tab) {
			tab.classList.toggle("active", tab.getAttribute("data-tab") === TAB_OF[name])
		})
		$("bar-label").textContent = title || __("Idea")
		backBtn.hidden = name !== "detail" && name !== "vote-detail"
	}

	// Every load bumps this; an answer that arrives after a newer load (another tab, Back, a new
	// search) is dropped, so it never renders into the view now shown.
	var loadSeq = 0
	function newLoad() {
		loadSeq += 1
		var seq = loadSeq
		return function stale() {
			return seq !== loadSeq
		}
	}

	// A dropped answer leaves the busy mark to the newer load of the same view, if that view is
	// still shown; otherwise nobody would clear it.
	function dropBusy(view, name) {
		if (currentView !== name) view.removeAttribute("aria-busy")
	}

	function route() {
		newLoad() // whatever was loading for the previous view is now stale
		var hash = location.hash.replace(/^#\/?/, "")
		var parts = hash.split("/")
		if (parts[0] === "ideas") {
			showView("ideas", __("My ideas"))
			loadIdeas()
		} else if (parts[0] === "idea" && parts[1]) {
			showView("detail", __("Idea"))
			loadDetail(decodeURIComponent(parts[1]))
		} else if (parts[0] === "vote" && parts[1]) {
			showView("vote-detail", __("Vote"))
			loadVoteDetail(decodeURIComponent(parts[1]))
		} else if (parts[0] === "vote") {
			showView("vote", __("Up for vote"))
			loadVotes()
		} else {
			showView("catch")
			focusText()
		}
	}
	window.addEventListener("hashchange", route)

	backBtn.addEventListener("click", function () {
		if (history.length > 1) history.back()
		else location.hash = currentView === "vote-detail" ? "#/vote" : "#/ideas"
	})

	function getOptions() {
		if (options) return Promise.resolve(options)
		return call(PC + "get_idea_options").then(function (result) {
			options = result
			return options
		})
	}

	function emptyRow(ul, message) {
		var li = document.createElement("li")
		li.className = "empty"
		li.textContent = message
		ul.appendChild(li)
	}

	// Ideas are shown as HTML: keep only plain formatting tags and a few safe attributes, so nothing
	// in a text can run. The list covers what the cockpit and Desk editors write (images, tables,
	// highlights), so an own idea edited here loses as little as possible.
	var ALLOWED =
		/^(P|BR|HR|B|STRONG|I|EM|U|S|DEL|STRIKE|MARK|SUB|SUP|UL|OL|LI|H1|H2|H3|H4|H5|H6|BLOCKQUOTE|CODE|PRE|A|SPAN|DIV|IMG|TABLE|THEAD|TBODY|TR|TH|TD)$/
	// The URL as the browser reads it: it drops tabs and line breaks anywhere and control characters
	// and spaces at the ends, so "/&#9;/host" would load from "//host". Check that, not the raw text.
	function plainUrl(value) {
		return value.replace(/[\t\n\r]/g, "").replace(/^[\u0000-\u0020]+|[\u0000-\u0020]+$/g, "")
	}
	// A path or URL on this site ("/files/…"); "//host" and "/\host" resolve to another host.
	function sameSite(value) {
		try {
			var url = new URL(plainUrl(value), location.href)
			return url.origin === location.origin && /^https?:$/.test(url.protocol)
		} catch (e) {
			return false
		}
	}
	// An uploaded file of this site: /files/… or /private/files/… (no "..", which the browser would
	// resolve to another path).
	function siteFile(value) {
		if (!sameSite(value)) return false
		var path = new URL(plainUrl(value), location.href).pathname
		return /^\/(private\/)?files\/[^/]/.test(path) && !/\/\.\.?(\/|$)|%2e/i.test(path)
	}
	function keepAttribute(tag, name, value) {
		if (tag === "A" && name === "href") return /^(https?:|mailto:)/i.test(plainUrl(value)) || sameSite(value)
		// Images only from this site's uploaded files: one from another host would tell it who read
		// the idea, and any other path here (/api/method/…) would be a request in the reader's name.
		if (tag === "IMG" && name === "src") return siteFile(value)
		if (tag === "IMG" && name === "alt") return true
		if ((tag === "TD" || tag === "TH") && (name === "colspan" || name === "rowspan")) return /^\d{1,2}$/.test(value)
		return false
	}
	function safeHtml(html) {
		var doc = new DOMParser().parseFromString("<div>" + (html || "") + "</div>", "text/html")
		var root = doc.body.firstChild
		;(function clean(node) {
			Array.prototype.slice.call(node.childNodes).forEach(function (child) {
				if (child.nodeType === 3) return
				if (child.nodeType !== 1 || !ALLOWED.test(child.tagName)) {
					child.replaceWith(doc.createTextNode(child.nodeType === 1 ? child.textContent : ""))
					return
				}
				Array.prototype.slice.call(child.attributes).forEach(function (attr) {
					if (!keepAttribute(child.tagName, attr.name, attr.value)) child.removeAttribute(attr.name)
				})
				if (child.tagName === "A") child.setAttribute("rel", "noopener noreferrer")
				clean(child)
			})
		})(root)
		return root.innerHTML
	}

	// -- My ideas --

	var ideasTimer = null
	$("ideas-search").placeholder = __("Search my ideas")
	$("ideas-search").addEventListener("input", function () {
		clearTimeout(ideasTimer)
		ideasTimer = setTimeout(loadIdeas, 250)
	})
	$("ideas-closed").addEventListener("change", loadIdeas)

	function loadIdeas() {
		var ul = $("ideas-list")
		var query = $("ideas-search").value.trim().toLowerCase()
		var stale = newLoad()
		call(PC + "get_ideas", { include_closed: $("ideas-closed").checked ? 1 : 0 })
			.then(function (ideas) {
				if (stale()) return
				ul.innerHTML = ""
				ideas
					.filter(function (idea) {
						return !query || (idea.title + " " + (idea.summary || "")).toLowerCase().indexOf(query) > -1
					})
					.forEach(function (idea) {
						ul.appendChild(ideaRow(idea, "#/idea/" + encodeURIComponent(idea.name)))
					})
				if (!ul.children.length) emptyRow(ul, query ? __("No idea matches.") : __("No ideas yet."))
			})
			.catch(function (error) {
				if (stale()) return
				ul.innerHTML = ""
				emptyRow(ul, error.message || __("No connection. Your ideas show when you are online."))
			})
	}

	function ideaRow(idea, href, right) {
		var li = document.createElement("li")
		li.className = "item"
		var a = document.createElement("a")
		a.className = "item-link"
		a.href = href
		var title = document.createElement("div")
		title.className = "item-title"
		title.textContent = idea.title
		a.appendChild(title)
		var meta = document.createElement("div")
		meta.className = "item-sub"
		var bits = [__(idea.stage)]
		if (idea.vote_status) bits.push(__("Open for vote"))
		if (idea.spawned_from_title) bits.push(__("from {0}", [idea.spawned_from_title]))
		meta.textContent = bits.join(" · ")
		a.appendChild(meta)
		if (idea.summary && idea.summary !== idea.title) {
			var summary = document.createElement("div")
			summary.className = "item-sub item-summary"
			summary.textContent = idea.summary
			a.appendChild(summary)
		}
		if (right) {
			var chip = document.createElement("span")
			chip.className = "chip" + (right.on ? " chip-on" : "")
			chip.textContent = right.text
			a.appendChild(chip)
		}
		li.appendChild(a)
		return li
	}

	// -- One of my ideas --

	var titleInput = $("d-title")
	var editor = $("d-content")
	var stageSelect = $("d-stage-select")
	var detailDirty = false
	// The text is shown cleaned (safeHtml); it is only sent back when it was edited here, so
	// saving a title or a stage never rewrites formatting this page can't show.
	var contentDirty = false

	function setDirty(dirty) {
		detailDirty = dirty
		if (!dirty) contentDirty = false
		$("d-save").disabled = !dirty
	}
	// The title wraps instead of being cut off; Enter does not add a line to it.
	function fitTitle() {
		titleInput.style.height = "auto"
		titleInput.style.height = titleInput.scrollHeight + "px"
	}
	titleInput.addEventListener("input", function () {
		setDirty(true)
		fitTitle()
	})
	titleInput.addEventListener("keydown", function (event) {
		if (event.key === "Enter") {
			event.preventDefault()
			editor.focus()
		}
	})
	editor.addEventListener("input", function () {
		contentDirty = true
		setDirty(true)
	})

	$("d-tools").addEventListener("mousedown", function (event) {
		event.preventDefault() // keep the selection in the editor
	})
	$("d-tools").addEventListener("click", function (event) {
		var button = event.target.closest("button")
		if (!button) return
		var cmd = button.getAttribute("data-cmd")
		editor.focus()
		if (cmd === "h3") document.execCommand("formatBlock", false, "h3")
		else document.execCommand(cmd)
		contentDirty = true
		setDirty(true)
	})

	function loadDetail(name) {
		var view = $("view-detail")
		if (!detail || detail.name !== name) {
			detail = null
			view.setAttribute("aria-busy", "true") // nothing of another idea flashes up
		}
		setDirty(false)
		var stale = newLoad()
		Promise.all([call(PC + "get_idea", { name: name }), getOptions()])
			.then(function (results) {
				if (stale()) return dropBusy(view, "detail")
				renderDetail(results[0])
				view.removeAttribute("aria-busy")
			})
			.catch(function (error) {
				if (stale()) return dropBusy(view, "detail")
				view.removeAttribute("aria-busy")
				toast(error.message || __("No connection. Your ideas show when you are online."))
			})
	}

	function renderDetail(idea) {
		detail = idea
		titleInput.value = idea.title
		requestAnimationFrame(fitTitle)
		editor.innerHTML = safeHtml(idea.content)
		setDirty(false)
		$("d-stage").textContent = __(idea.stage)
		$("d-job").textContent = idea.stage_job ? __(idea.stage_job) : ""
		stageSelect.innerHTML = ""
		options.stages.forEach(function (stage) {
			var option = document.createElement("option")
			option.value = stage
			option.textContent = __(stage)
			option.selected = stage === idea.stage
			stageSelect.appendChild(option)
		})
		var next = nextStage(idea.stage)
		$("d-grow").hidden = !next
		if (next) $("d-grow").textContent = __("Grow to {0}", [__(next)])
		renderOwnVote(idea)
	}

	// The next stage on the way to Harvest; Compost and Harvest have none.
	function nextStage(stage) {
		var growing = options.stages.filter(function (s) {
			return options.closed_stages.indexOf(s) === -1 || s === "Harvest"
		})
		var i = growing.indexOf(stage)
		return i > -1 && i < growing.length - 1 ? growing[i + 1] : null
	}

	function saveDetail(changes) {
		var args = Object.assign({ name: detail.name, modified: detail.modified }, changes)
		return call(PC + "update_idea", args, true)
			.then(function (idea) {
				renderDetail(idea)
				return idea
			})
			.catch(function (error) {
				toast(
					error.excType === "TimestampMismatchError"
						? __("This idea was changed elsewhere. Reload it to see the latest version.")
						: error.message || __("No connection. Try again when you are online.")
				)
				throw error
			})
	}

	$("d-save").addEventListener("click", function () {
		var title = titleInput.value.trim()
		if (!title) {
			toast(__("Title is required"))
			return
		}
		var changes = { title: title }
		if (contentDirty) changes.content = editor.innerHTML
		saveDetail(changes)
			.then(function () {
				toast(__("Saved"))
			})
			.catch(function () {}) // saveDetail has shown the reason
	})

	function changeStage(stage) {
		if (!detail || stage === detail.stage) return
		// Unsaved text goes along, so a stage change never drops an edit.
		var changes = { stage: stage }
		if (detailDirty) changes.title = titleInput.value.trim() || detail.title
		if (contentDirty) changes.content = editor.innerHTML
		saveDetail(changes)
			.then(function (idea) {
				toast(__("Now {0}", [__(idea.stage)]))
			})
			.catch(function () {
				// Refused or offline: the picker shows the stage the idea really has again.
				stageSelect.value = detail.stage
			})
	}
	$("d-grow").addEventListener("click", function () {
		changeStage(nextStage(detail.stage))
	})
	stageSelect.addEventListener("change", function () {
		changeStage(stageSelect.value)
	})

	var addBox = $("d-add")
	addBox.placeholder = __("Another thought on this idea …")
	addBox.addEventListener("input", function () {
		$("d-add-btn").disabled = !addBox.value.trim()
	})
	$("d-add-btn").addEventListener("click", function () {
		if (detailDirty) {
			toast(__("Save your changes first."))
			return
		}
		call("add_to_idea", { name: detail.name, text: addBox.value }, true)
			.then(function (idea) {
				addBox.value = ""
				$("d-add-btn").disabled = true
				renderDetail(idea)
				toast(__("Added"))
			})
			.catch(function (error) {
				toast(error.message || __("No connection. Try again when you are online."))
			})
	})

	function renderOwnVote(idea) {
		var open = idea.vote_status === "Open for vote"
		$("d-vote-state").textContent = open
			? idea.vote_count === 1
				? __("Open for vote · 1 vote")
				: __("Open for vote · {0} votes", [idea.vote_count])
			: __("Only you can see this idea.")
		var toggle = $("d-vote-toggle")
		toggle.hidden = !open && idea.stage === "Compost"
		toggle.textContent = open ? __("Withdraw from vote") : __("Hand in for Vote")
	}

	$("d-vote-toggle").addEventListener("click", function () {
		var open = detail.vote_status === "Open for vote"
		var question = open
			? __("Withdraw this idea from the vote? The votes so far are removed.")
			: __(
					"Hand in this idea for a vote? Every cockpit user can then read it and vote for it. Your writing sessions and history stay private."
			  )
		if (!window.confirm(question)) return
		call(PC + (open ? "withdraw_idea_from_vote" : "hand_in_idea_for_vote"), { name: detail.name }, true)
			.then(renderDetail)
			.catch(function (error) {
				toast(error.message || __("No connection. Try again when you are online."))
			})
	})

	// -- Vote --

	function voteChip(row) {
		return { text: (row.voted ? "♥ " : "♡ ") + row.vote_count, on: row.voted }
	}

	function loadVotes() {
		var ul = $("vote-list")
		var stale = newLoad()
		call(PC + "get_ideas_for_vote")
			.then(function (rows) {
				if (stale()) return
				ul.innerHTML = ""
				rows.forEach(function (row) {
					var li = ideaRow(
						{ title: row.title, summary: row.summary, stage: row.stage },
						"#/vote/" + encodeURIComponent(row.name),
						voteChip(row)
					)
					var by = row.mine ? __("Your idea") : row.author ? row.author.full_name : ""
					if (by) li.querySelector(".item-sub").textContent += " · " + by
					ul.appendChild(li)
				})
				if (!rows.length) emptyRow(ul, __("No idea is up for vote right now."))
			})
			.catch(function (error) {
				if (stale()) return
				ul.innerHTML = ""
				emptyRow(ul, error.message || __("No connection. Try again when you are online."))
			})
	}

	var voting = null // the idea open on #/vote/<name>

	function loadVoteDetail(name) {
		var view = $("view-vote-detail")
		if (!voting || voting.name !== name) view.setAttribute("aria-busy", "true")
		var stale = newLoad()
		call(PC + "get_idea_for_vote", { name: name })
			.then(function (row) {
				if (stale()) return dropBusy(view, "vote-detail")
				renderVoteDetail(row)
				view.removeAttribute("aria-busy")
			})
			.catch(function (error) {
				if (stale()) return dropBusy(view, "vote-detail")
				view.removeAttribute("aria-busy")
				toast(error.message || __("No connection. Try again when you are online."))
			})
	}

	function renderVoteDetail(row) {
		voting = row
		$("v-title").textContent = row.title
		var bits = [__(row.stage)]
		if (row.author && !row.mine) bits.push(row.author.full_name)
		bits.push(row.vote_count === 1 ? __("1 vote") : __("{0} votes", [row.vote_count]))
		$("v-meta").textContent = bits.join(" · ")
		$("v-content").innerHTML = safeHtml(row.content)
		var button = $("v-vote")
		if (row.mine) {
			button.textContent = __("Your idea")
			button.disabled = true
		} else {
			button.disabled = false
			button.textContent = row.voted ? __("Take back my vote") : __("Vote for this idea")
			button.classList.toggle("btn-voted", row.voted)
		}
	}

	$("v-vote").addEventListener("click", function () {
		if (!voting || voting.mine) return
		call(PC + "vote_idea", { name: voting.name }, true)
			.then(function (result) {
				voting.voted = result.voted
				voting.vote_count = result.vote_count
				renderVoteDetail(voting)
			})
			.catch(function (error) {
				toast(error.message || __("No connection. Try again when you are online."))
			})
	})

	renderQueue(readQueue())
	updateSave()
	flush()
	route()
})()
