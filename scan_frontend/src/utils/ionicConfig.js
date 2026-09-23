import { isPlatform } from "@ionic/vue"
import { createAnimation, iosTransitionAnimation } from "@ionic/core"

export const animationBuilder = (baseEl, opts) => {
	if (opts.direction === "back") {
		return createAnimation()
	}
	return iosTransitionAnimation(baseEl, opts)
}

const getIonicConfig = () => {
	const config = { mode: "ios" }

	if (isPlatform("iphone")) {
		config.swipeBackEnabled = false
		config.navAnimation = animationBuilder
	}

	return config
}

export default getIonicConfig
