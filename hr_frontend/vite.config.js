import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import path from "path"
import fs from "fs"

export default defineConfig({
	server: {
		port: 8082,
		proxy: getProxyOptions(),
		allowedHosts: true,
	},
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
			"@iown": path.resolve(__dirname, "../frontend/src"),
			"frappe-gantt/src/gantt.scss": path.resolve(__dirname, "src/lib/empty.scss"),
		},
	},
	build: {
		outDir: "../phamos/public/hr",
		emptyOutDir: true,
		target: "es2015",
		sourcemap: true,
		rollupOptions: {
			output: {
				manualChunks: {
					"frappe-ui": ["frappe-ui"],
				},
			},
		},
	},
	optimizeDeps: {
		include: ["frappe-ui > feather-icons", "tailwind.config.js", "frappe-gantt"],
	},
})

function getProxyOptions() {
	const config = getCommonSiteConfig()
	const webserver_port = config ? config.webserver_port : 8000
	return {
		"^/(app|login|api|assets|files|private)": {
			target: `http://127.0.0.1:${webserver_port}`,
			ws: true,
			router: function (req) {
				const site_name = req.headers.host.split(":")[0]
				return `http://${site_name}:${webserver_port}`
			},
		},
	}
}

function getCommonSiteConfig() {
	let currentDir = path.resolve(".")
	while (currentDir !== "/") {
		if (
			fs.existsSync(path.join(currentDir, "sites")) &&
			fs.existsSync(path.join(currentDir, "apps"))
		) {
			const configPath = path.join(currentDir, "sites", "common_site_config.json")
			if (fs.existsSync(configPath)) {
				return JSON.parse(fs.readFileSync(configPath))
			}
			return null
		}
		currentDir = path.resolve(currentDir, "..")
	}
	return null
}
