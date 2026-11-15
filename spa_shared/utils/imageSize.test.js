import { clampImageWidth, normalizeImageSize, parseImageWidth } from "./imageSize.js"

describe("parseImageWidth", () => {
	it("reads the width attribute or an inline px width", () => {
		expect(parseImageWidth({ widthAttr: "300" })).toBe(300)
		expect(parseImageWidth({ widthAttr: "", styleWidth: "250px" })).toBe(250)
		expect(parseImageWidth({ widthAttr: "120.6" })).toBe(121)
	})
	it("leaves percentages, other units and nothing alone", () => {
		expect(parseImageWidth({ styleWidth: "50%" })).toBeNull()
		expect(parseImageWidth({ widthAttr: "10em" })).toBeNull()
		expect(parseImageWidth({})).toBeNull()
	})
})

describe("clampImageWidth", () => {
	it("keeps the width between the minimum and the field", () => {
		expect(clampImageWidth(10, 600)).toBe(40)
		expect(clampImageWidth(900, 600)).toBe(600)
		expect(clampImageWidth(321.4, 600)).toBe(321)
		expect(clampImageWidth(321, undefined)).toBe(321)
	})
})

describe("normalizeImageSize", () => {
	it("falls back to large", () => {
		expect(normalizeImageSize("small")).toBe("small")
		expect(normalizeImageSize("huge")).toBe("large")
		expect(normalizeImageSize(undefined)).toBe("large")
	})
})
