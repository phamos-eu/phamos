// Debug only (phriend.hands()): every gesture next to a small Phriend, on the side it is attached
// (GESTURES side, PM 2026-11-21). Switch a side to try it on the real Phriend, then copy the
// table and hand it to the developer. Changes live in memory until the page reloads.

import { GESTURES } from "./ball";

const CSS = `
.hp { position: fixed; left: 16px; bottom: 16px; width: 400px; max-width: calc(100vw - 32px); max-height: calc(100vh - 32px); overflow: auto;
	padding: 10px 12px; border-radius: 12px; background: var(--ph-bg); color: var(--ph-text);
	border: 1px solid var(--ph-border); box-shadow: var(--ph-shadow); font-size: 13px; z-index: 2; }
.hp h3 { margin: 0 0 2px; font-size: 14px; }
.hp p { margin: 0 0 8px; color: var(--ph-muted); font-size: 12px; }
.hp-row { display: grid; grid-template-columns: 70px minmax(0, 1fr) auto; align-items: center; gap: 8px; padding: 4px 0;
	border-top: 1px solid var(--ph-border); }
.hp-mini { position: relative; height: 34px; }
.hp-ball { position: absolute; left: 22px; top: 2px; width: 30px; height: 30px; border-radius: 50%;
	background: radial-gradient(circle at 35% 30%, #4a4a4a, #151515 45%, #000); }
.hp-emoji { position: absolute; top: 12px; font-size: 18px; line-height: 1;
	font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif; }
.hp-emoji.left { left: 6px; } .hp-emoji.right { left: 44px; }
.hp-name small { display: block; color: var(--ph-muted); }
.hp-sides { display: flex; gap: 4px; }
.hp button { padding: 3px 8px; border: 1px solid var(--ph-border); border-radius: 6px; background: transparent;
	color: inherit; font: inherit; font-size: 12px; white-space: nowrap; cursor: pointer; }
.hp button[aria-pressed="true"] { background: var(--ph-accent); color: var(--ph-on-accent); border-color: var(--ph-accent); }
.hp-foot { display: flex; justify-content: space-between; gap: 8px; margin-top: 8px; }
`;

export function open_hands_panel(ball, react) {
	const existing = ball.shadow.querySelector(".hp");
	if (existing) return existing.remove();
	ball.side_overrides = ball.side_overrides || {};
	if (!ball.shadow.querySelector("style[data-hp]")) {
		const style = document.createElement("style");
		style.dataset.hp = "1";
		style.textContent = CSS;
		ball.shadow.appendChild(style);
	}
	const panel = document.createElement("div");
	panel.className = "hp";
	panel.innerHTML = `<h3>Phriend hands: which side?</h3>
		<p>The side where the emoji's wrist, arm or flame meets Phriend. "Auto" = the side facing into the window.</p>`;

	const side_of = (name) => ball.side_overrides[name] || GESTURES[name].side || "auto";
	for (const [name, g] of Object.entries(GESTURES)) {
		const row = document.createElement("div");
		row.className = "hp-row";
		const mini = document.createElement("div");
		mini.className = "hp-mini";
		mini.innerHTML = `<span class="hp-ball"></span><span class="hp-emoji"></span>`;
		mini.querySelector(".hp-emoji").textContent = g.hand;
		const label = document.createElement("div");
		label.className = "hp-name";
		label.textContent = name;
		const small = document.createElement("small");
		label.appendChild(small);
		const sides = document.createElement("div");
		sides.className = "hp-sides";
		const buttons = ["left", "auto", "right"].map((side) => {
			const b = document.createElement("button");
			b.type = "button";
			b.textContent = side === "left" ? "◀ Left" : side === "right" ? "Right ▶" : "Auto";
			b.addEventListener("click", () => {
				ball.side_overrides[name] = side;
				refresh();
				react(name);
			});
			sides.appendChild(b);
			return [side, b];
		});
		const refresh = () => {
			const side = side_of(name);
			const shown = side === "auto" ? ball.inner_side || "left" : side;
			mini.querySelector(".hp-emoji").className = `hp-emoji ${shown}`;
			small.textContent = side === "auto" ? `auto (${shown} here)` : side;
			buttons.forEach(([s, b]) => b.setAttribute("aria-pressed", String(s === side)));
		};
		refresh();
		mini.addEventListener("click", () => react(name));
		mini.title = "Play it on Phriend";
		row.append(mini, label, sides);
		panel.appendChild(row);
	}

	const foot = document.createElement("div");
	foot.className = "hp-foot";
	const copy = document.createElement("button");
	copy.type = "button";
	copy.textContent = "Copy sides";
	copy.addEventListener("click", async () => {
		const table = {};
		for (const name of Object.keys(GESTURES)) {
			table[name] = side_of(name);
		}
		const text = JSON.stringify(table, null, 1);
		try {
			await navigator.clipboard.writeText(text);
			copy.textContent = "Copied ✓";
		} catch (e) {
			console.log(text);
			copy.textContent = "In the console";
		}
	});
	const close = document.createElement("button");
	close.type = "button";
	close.textContent = "Close";
	close.addEventListener("click", () => panel.remove());
	foot.append(copy, close);
	panel.appendChild(foot);
	ball.shadow.appendChild(panel);
}
