// Styles of the report flow, added to Phriend's Shadow DOM when the flow first opens.
// Colours come from the variables in ball.js, so light and dark follow the host.

export const FLOW_CSS = `
.overlay {
	position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
	padding: 24px; background: rgba(15, 15, 15, 0.45); animation: fade 0.14s ease-out;
}
.panel {
	width: min(980px, 100%); max-height: calc(100vh - 48px); display: flex; flex-direction: column;
	background: var(--ph-bg); color: var(--ph-text); border: 1px solid var(--ph-border);
	border-radius: 14px; box-shadow: var(--ph-shadow); overflow: hidden; animation: rise 0.16s ease-out;
}
.panel.narrow { width: min(620px, 100%); }
header { display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--ph-border); }
header svg.mini { width: 26px; height: 31px; flex: none; }
.heading { flex: 1; min-width: 0; }
.heading h2 { margin: 0; font-size: 16px; font-weight: 600; }
.heading p { margin: 0; font-size: 12px; color: var(--ph-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dots { display: flex; gap: 6px; }
.dot { width: 9px; height: 9px; padding: 0; border: 0; border-radius: 50%; background: var(--ph-border-strong); cursor: pointer; }
.dot.on { background: var(--ph-accent); }
.dot:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible {
	outline: 2px solid var(--ph-focus); outline-offset: 2px;
}
.icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0;
	border: 0; border-radius: 8px; background: transparent; color: var(--ph-muted); cursor: pointer; }
.icon-btn:hover { background: var(--ph-surface); color: var(--ph-text); }
main { flex: 1; min-height: 0; overflow: auto; padding: 18px; }
.pane[hidden] { display: none; }
footer { display: flex; align-items: center; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--ph-border); }
footer .grow { flex: 1; }
footer .hint { font-size: 12px; color: var(--ph-muted); }
footer .shortcut-link { font-size: 12px; color: var(--ph-muted); text-decoration: none; }
footer .shortcut-link:hover { color: var(--ph-text); text-decoration: underline; }
footer .shortcut-link[hidden] { display: none; }
button.btn { height: 34px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--ph-border-strong);
	background: transparent; color: var(--ph-text); font: inherit; font-weight: 500; cursor: pointer; }
button.btn:hover { background: var(--ph-surface); }
button.btn.primary { background: var(--ph-accent); color: var(--ph-on-accent); border-color: var(--ph-accent); }
button.btn.primary:hover { opacity: 0.9; }
button.btn.ghost { border-color: transparent; color: var(--ph-muted); }
button.btn.ghost:hover { color: var(--ph-text); }
button.btn.danger { background: var(--ph-danger); border-color: var(--ph-danger); color: #fff; }
button.btn[hidden] { display: none; }
button.btn.with-icon { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; font-size: 13px; }
button.btn.with-icon svg { flex: none; }
label.field { display: block; font-size: 13px; color: var(--ph-muted); margin: 0 0 6px; }
input.input, textarea.input { width: 100%; padding: 9px 11px; border: 1px solid var(--ph-border-strong); border-radius: 8px;
	background: var(--ph-bg); color: var(--ph-text); font: inherit; font-size: 15px; outline: none; }
textarea.input { resize: vertical; min-height: 120px; line-height: 1.5; }
input.input:focus, textarea.input:focus { border-color: var(--ph-focus); }
.input::placeholder { color: var(--ph-muted); opacity: 0.8; }
.gap { height: 16px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-width: 120px; padding: 10px 14px;
	border: 1px solid var(--ph-border-strong); border-radius: 10px; background: transparent; color: var(--ph-text);
	font: inherit; text-align: left; cursor: pointer; }
.chip small { color: var(--ph-muted); font-size: 12px; }
.chip:hover { background: var(--ph-surface); }
.chip.on { background: var(--ph-chip); border-color: var(--ph-chip-border); color: var(--ph-chip-text); }
.chip.on small { color: var(--ph-chip-text); }
.chip.slim { min-width: 0; padding: 7px 16px; }
.reported { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--ph-border); }
.reported[hidden] { display: none; }
.reported-head { margin: 0 0 8px; font-size: 13px; color: var(--ph-muted); }
.reported-count { display: inline-block; min-width: 18px; padding: 0 6px; border-radius: 9px; background: var(--ph-surface);
	color: var(--ph-text); font-size: 12px; text-align: center; }
.reported-empty { margin: 0; font-size: 13px; color: var(--ph-muted); }
.reported ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.reported a { display: grid; grid-template-columns: auto minmax(0, 1fr); column-gap: 8px; padding: 6px 8px; border-radius: 8px;
	color: var(--ph-text); text-decoration: none; }
.reported a:hover { background: var(--ph-surface); }
.reported a:focus-visible { outline: 2px solid var(--ph-focus); outline-offset: 1px; }
.reported-type { grid-row: span 2; align-self: start; margin-top: 1px; padding: 1px 6px; border-radius: 6px; font-size: 11px;
	background: var(--ph-chip); color: var(--ph-chip-text); }
.reported-title { font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.reported-meta { font-size: 12px; color: var(--ph-muted); }
.reported-all { margin: 6px 8px 0; font-size: 13px; color: var(--ph-muted); }
.shot { position: relative; }
.skeleton { display: flex; align-items: center; justify-content: center; gap: 10px; height: min(52vh, 460px);
	border: 1px dashed var(--ph-border-strong); border-radius: 10px; color: var(--ph-muted);
	background: linear-gradient(100deg, var(--ph-surface) 40%, var(--ph-bg) 50%, var(--ph-surface) 60%) 0 0 / 200% 100%;
	animation: shimmer 1.2s linear infinite; }
.spinner { width: 16px; height: 16px; border: 2px solid var(--ph-border-strong); border-top-color: var(--ph-text);
	border-radius: 50%; animation: spin 0.8s linear infinite; }
.no-shot { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center;
	height: 180px; border: 1px dashed var(--ph-border-strong); border-radius: 10px; color: var(--ph-muted); }
.shot-bar { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 13px; color: var(--ph-muted); }
.shot-bar .grow { flex: 1; }
.annotator { display: flex; gap: 10px; align-items: flex-start; }
.tools { display: flex; flex-direction: column; gap: 6px; }
.tool-gap { height: 6px; }
.tool { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; padding: 0;
	border: 1px solid var(--ph-border-strong); border-radius: 8px; background: transparent; color: var(--ph-text); cursor: pointer; }
.tool:hover { background: var(--ph-surface); }
.tool.on { background: var(--ph-chip); border-color: var(--ph-chip-border); color: var(--ph-chip-text); }
.canvas-wrap { position: relative; flex: 1; min-width: 0; max-height: min(58vh, 560px); overflow: auto;
	border: 1px solid var(--ph-border); border-radius: 10px; background: var(--ph-surface); }
.canvas-wrap canvas { display: block; width: 100%; height: auto; cursor: crosshair; touch-action: none; }
.text-input { position: absolute; min-width: 180px; padding: 2px 6px; font: 600 18px/1.2 var(--ph-font); color: var(--ph-red);
	background: rgba(255, 255, 255, 0.95); border: 2px solid var(--ph-red); border-radius: 4px; outline: none; z-index: 1;
	transform: translate(-6px, -4px); }
.summary { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 18px; align-items: start; }
.summary h3 { margin: 0 0 4px; font-size: 17px; font-weight: 600; }
.summary h3.built { color: var(--ph-muted); font-weight: 500; }
.meta { margin: 0 0 14px; font-size: 13px; color: var(--ph-muted); }
.comment { margin: 0 0 14px; white-space: pre-wrap; font-size: 14px; }
.thumb { width: 100%; border: 1px solid var(--ph-border); border-radius: 8px; display: block; }
.facts-title { margin: 0 0 4px; font-size: 12px; color: var(--ph-muted); }
.fact { display: flex; justify-content: space-between; gap: 16px; padding: 6px 0; border-top: 1px solid var(--ph-border); font-size: 13px; }
.fact span:first-child { color: var(--ph-muted); flex: none; }
.fact span:last-child { text-align: right; overflow-wrap: anywhere; }
details { margin-top: 10px; font-size: 13px; }
summary { cursor: pointer; color: var(--ph-muted); }
pre { max-height: 220px; overflow: auto; padding: 10px; border-radius: 8px; background: var(--ph-surface);
	font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.confirm { font-size: 14px; }
@keyframes fade { from { opacity: 0; } }
@keyframes rise { from { opacity: 0; transform: translateY(8px) scale(0.99); } }
@keyframes shimmer { to { background-position: -200% 0; } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) {
	.overlay { padding: 0; align-items: stretch; }
	.panel, .panel.narrow { max-height: 100vh; border-radius: 0; border: 0; }
	.annotator { flex-direction: column; }
	.tools { flex-direction: row; }
	.summary { grid-template-columns: 1fr; }
	footer .hint { display: none; }
}
@media (prefers-reduced-motion: reduce) {
	.overlay, .panel { animation: none; }
	.skeleton { animation: none; }
}
`;
