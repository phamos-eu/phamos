<template>
	<!-- Ophice (#2053, #2070): its own app at /ophice, full screen. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1 text-ink-gray-9">
		<!-- Ophice's background, one for everyone (#2053); the button is in the right sidebar. -->
		<input
			ref="backgroundInput"
			type="file"
			accept="image/png,image/jpeg,image/webp,image/gif"
			class="hidden"
			@change="uploadBackground"
		/>

		<div class="flex min-h-0 flex-1">
		<!-- People (#2063): everyone with Raven, online first; click one to chat. -->
		<PeopleSidebar
			v-if="me"
			ref="peopleSidebar"
			:pinned="showPeople"
			@pin="setPeoplePinned"
			:people="people"
			:me="me.user"
			:hide-details="hideDetails"
			:now="clock"
			:meeting="meetingArea"
			:area-of="areaOfUser"
			:auto-cockpit="autoCockpit"
			@auto-cockpit="setAutoCockpit"
			@pick="(person, event) => openChatWith(person, event)"
			@hide="setHideDetails"
		/>
		<div
			id="ophice-stage"
			ref="stage"
			class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4"
		>
			<!--
				Adjust (#2058, #2089): the image in grid tiles (drag it on the map, or nudge it here), the
				grid's size, and everyone's starting zoom. Top left; everyone sees the changes.
			-->
			<div
				v-if="adjustingBackground && me"
				class="absolute left-6 top-6 z-30 w-72 space-y-3 rounded-xl border border-outline-gray-2 bg-surface-white p-3 text-sm text-ink-gray-9 shadow-xl"
				data-no-pan
				data-testid="background-adjust"
			>
				<template v-if="background && imageBox">
					<div class="flex items-center justify-between">
						<span class="font-medium">{{ __("Background image") }}</span>
						<Button variant="ghost" :disabled="backgroundLayout.fit" @click="setLayout({ fit: true })">
							{{ __("Fit") }}
						</Button>
					</div>
					<p class="text-xs text-ink-gray-5">
						{{ __("Drag the image on the map to move it, a corner to resize it (half tiles; Alt: free). Arrow keys: 1 px, with Shift half a tile.") }}
					</p>
					<div class="grid grid-cols-3 gap-2 text-xs">
						<label v-for="field in IMAGE_FIELDS" :key="field.key" class="block">
							<span class="text-ink-gray-6">{{ field.label }}</span>
							<div class="mt-0.5 flex items-center">
								<button type="button" class="ophice-zoom__button" :title="__('Half a tile less')" @click="nudgeImage(field.key, -0.5)">
									<FeatherIcon name="minus" class="h-3 w-3" />
								</button>
								<span class="w-9 text-center tabular-nums" :data-testid="`background-${field.key}`">{{ fmtTiles(imageBox[field.key]) }}</span>
								<button type="button" class="ophice-zoom__button" :title="__('Half a tile more')" @click="nudgeImage(field.key, 0.5)">
									<FeatherIcon name="plus" class="h-3 w-3" />
								</button>
							</div>
						</label>
					</div>
				</template>
				<div class="space-y-1.5 border-t border-outline-gray-2 pt-2" :class="{ 'border-t-0 pt-0': !background }">
					<span class="font-medium">{{ __("Grid") }}</span>
					<div class="flex items-center gap-2 text-xs">
						<label v-for="axis in GRID_AXES" :key="axis.key" class="flex items-center gap-1">
							<span class="text-ink-gray-6">{{ axis.label }}</span>
							<button type="button" class="ophice-zoom__button" :disabled="gridBusy" :title="__('One tile less')" @click="changeGrid(axis.key, -1)">
								<FeatherIcon name="minus" class="h-3 w-3" />
							</button>
							<span class="w-7 text-center tabular-nums" :data-testid="`grid-${axis.key}`">{{ me[axis.key] }}</span>
							<button type="button" class="ophice-zoom__button" :disabled="gridBusy" :title="__('One tile more')" @click="changeGrid(axis.key, 1)">
								<FeatherIcon name="plus" class="h-3 w-3" />
							</button>
						</label>
					</div>
					<Button
						v-if="background && imageBox"
						size="sm"
						variant="subtle"
						:loading="gridBusy"
						:title="__('Grows the grid to the right and down until it covers the image')"
						data-testid="grid-cover-image"
						@click="gridToImage"
					>
						{{ __("Grid to cover the image") }}
					</Button>
				</div>
				<div class="flex items-center justify-between gap-2 border-t border-outline-gray-2 pt-2 text-xs">
					<span class="text-ink-gray-6">{{ __("Starting zoom for everyone: {0} %", [Math.round((backgroundLayout.zoom || 1) * 100)]) }}</span>
					<Button size="sm" variant="ghost" :disabled="!background" data-testid="zoom-for-everyone" @click="setLayout({ zoom: mainCam.zoom.value })">
						{{ __("Use mine") }}
					</Button>
				</div>
				<p class="text-xs text-ink-gray-5">{{ __("Everyone sees the change.") }}</p>
			</div>
			<!-- The meeting of the area I stand in (#2060), top right. -->
			<!-- Meeting view (#2061): the meeting is the big window, the map shrinks to the bottom left. -->
			<!-- The same window all along (#2075): moving it to another place in the page would restart the call. -->
			<Teleport :to="pipBody || 'body'" :disabled="!pipBody">
			<MeetingPanel
				v-if="meetingArea"
				ref="meetingPanel"
				:class="cockpitOpen ? 'z-[61]' : 'z-30'"
				:area="meetingArea"
				:display-name="me?.full_name"
				:bounds="cockpitOpen ? viewport : view"
				:rect="cockpitOpen ? floatRect : meetingRect || defaultMeetingRect()"
				:floating="cockpitOpen"
				:pip="Boolean(pipBody)"
				:dock="cockpitOpen ? dockRects?.video : inTiles ? tileRects.video : null"
				:hue="meetingArea.color_hue"
				:limit-hint="meetingArea.jitsi_domain === 'meet.jit.si' && !(inTiles && mapBig)"
				:popped-out="poppedOut === meetingArea.name"
				:window-closed="meetingWindowClosed"
				@update:rect="(rect) => (cockpitOpen ? setFloatRect(rect) : setMeetingRect(rect))"
				@leave="leaveMeeting(true)"
				@popout="popOut"
				@bring-back="bringBack"
				@float="floatMeeting"
			/>
			</Teleport>
			<StatusMenu
				v-if="statusOpen && me"
				:class="statusAt ? 'fixed z-50' : 'absolute right-6 top-6 z-40'"
				:style="statusAt ? statusMenuStyle : null"
				:status="me.status"
				:on-save="saveStatus"
				@close="statusOpen = false"
			/>
			<!-- The area's chat (#2062), above the mini map. -->
			<!-- Left column: the people in the meeting huddle above its chat (#2067). -->
			<Teleport :to="pipBody || 'body'" :disabled="!pipBody">
			<div
				v-if="meetingArea && me"
				class="flex flex-col gap-2 rounded-2xl p-2"
				:class="
					cockpitOpen && dockRects?.chat
						? 'fixed z-[61]'
						: pipBody
							? 'relative min-h-0 flex-1'
							: cockpitOpen
								? 'fixed z-[55] shadow-2xl'
								: inTiles
									? 'z-20'
									: 'absolute z-20'
				"
				:style="{
					...(cockpitOpen && dockRects?.chat
						? dockRects.chat.hidden
							? { display: 'none' }
							: rectPx(dockRects.chat)
						: pipBody
							? {}
							: cockpitOpen
								? floatingColumnStyle
								: areaChatStyle),
					...meetingFrameStyle,
				}"
				data-testid="meeting-column"
			>
				<!-- In the mini map the map shows who is there; the chat gets the room. -->
				<MeetingHuddle
					v-if="!(cockpitOpen && dockRects?.chat)"
					:area="meetingArea"
					:people="huddle"
					:me="me.user"
					@pick="(person, event) => openChatWith(person, event)"
				/>
				<!-- Guest and customer meeting areas: the guest chat, kept only for a short while (#2083). -->
				<GuestChat
					v-if="GUEST_KINDS.includes(meetingArea.kind)"
					:key="`guest-chat-${meetingArea.name}`"
					class="min-h-0 flex-1"
					:title="meetingArea.title"
					:messages="guestChat.area === meetingArea.name ? guestChat.messages : []"
					:me="me.user"
					:on-send="sendGuestChat"
				/>
				<AreaChat
					v-else
					:key="meetingArea.name"
					class="min-h-0 flex-1"
					:area="meetingArea"
					:me="me.user"
					:name-of="nameOf"
					:socket="socket"
				/>
			</div>
			</Teleport>
			<AreaDialog :area="areaDraft" :on-save="saveArea" :on-delete="deleteArea" @close="areaDraft = null" />
			<p
				v-if="editingAreas"
				class="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full bg-black/75 px-3 py-1 text-xs text-white"
			>
				{{ __("Drag on the grid to mark a meeting area, click an area to edit it") }}
			</p>
			<!--
				Burn and chat notices (#2057, #2066) sit where they happened, on the map (PM): at their
				space, or next to my chip. In the meeting view (small map) they wait at the bottom right.
			-->
			<div
				v-if="meetingArea && (noticeList.length || batchNoticeList.length)"
				class="pointer-events-none absolute bottom-6 right-6 z-30 flex flex-col items-end gap-2"
				data-testid="notice-stack"
			>
				<BatchNotice
					v-for="notice in batchNoticeList"
					:key="`batch-${notice.name}`"
					class="pointer-events-auto"
					:notice="notice"
					:now="clock"
					:busy="batchBusy[notice.name] || ''"
					@vote="(choice) => voteBatch(notice, choice)"
					@dismiss="dismissedBatches.add(notice.name)"
				/>
				<BurnNotice
					v-for="notice in noticeList"
					:key="notice.encounter"
					class="pointer-events-auto"
					:notice="notice"
					:now="now"
					:saving="notice.saving"
					@save="saveEncounter(notice)"
				/>
			</div>
			<!--
				The map (#2089): a view onto a canvas that can be bigger than the window. Drag or scroll to
				look around (it bounces at the edges), Ctrl/⌘ + scroll or the buttons to zoom. In a meeting
				it is the mini map at the bottom left, with its own zoom. The canvas holds the background
				image (it may reach beyond the grid; those parts are dimmed) and the walkable grid.
			-->
			<div
				v-if="me"
				class="ophice-viewport overflow-hidden"
				:class="meetingArea ? (inTiles ? 'z-20 rounded-xl bg-surface-gray-2' : 'absolute z-20 rounded-lg border border-outline-gray-2 bg-surface-gray-2 shadow-xl') : 'absolute inset-0'"
				:style="viewportStyle"
				data-testid="map-viewport"
				@pointerdown="onViewportDown"
				@pointermove="camera().onPointerMove"
				@pointerup="camera().onPointerUp"
				@pointercancel="camera().onPointerUp"
				@click.capture="camera().onClickCapture"
				@dblclick="onViewportDblclick"
				@wheel="onViewportWheel"
			>
			<div
				class="ophice-canvas absolute left-0 top-0"
				:class="{ 'ophice-canvas--spring': camera().springing.value, 'ophice-canvas--dragging': camera().dragging.value }"
				:style="canvasStyle"
				data-testid="map-canvas"
			>
				<BackgroundImage
					v-if="background && imageBox"
					:src="background"
					:placement="imageBox"
					:canvas="camera().canvas.value"
					:tile="tile"
				/>
				<MapFog
					v-if="background && imageBox"
					:canvas="camera().canvas.value"
					:revealed="{ x: 0, y: 0, w: me.cols, h: me.rows }"
					:tile="tile"
				/>
			<div
				class="ophice-grid absolute"
				:class="{
					'ophice-grid--plain rounded-lg border border-outline-gray-2 bg-surface-white': !background,
					'ophice-grid--lines': editingAreas || adjustingBackground,
				}"
				:style="gridStyle"
				data-testid="map-grid"
			>
				<AreaLayer
					:areas="areas"
					:tile="tile"
					:cols="me.cols"
					:rows="me.rows"
					:editing="editingAreas"
					:active-name="meetingArea?.name || ''"
					@draw="(rect) => (areaDraft = { ...rect })"
					@pick="(area) => (areaDraft = { ...area })"
					@change="reshapeArea"
				/>
				<!-- Perimeters (#2056): touching circles = in conversation. Below the chips, no clicks. -->
				<div
					v-for="chip in perimeterList"
					:key="`perimeter-${chip.user}`"
					class="ophice-perimeter pointer-events-none absolute rounded-full"
					:class="{
						'ophice-perimeter--me': chip.mine,
						'ophice-perimeter--contact': chip.contact,
						'ophice-chip--remote': !chip.mine,
						'ophice-chip--lift': lifts[chip.user],
					}"
					:style="perimeterStyle(chip)"
					:data-testid="chip.mine ? 'my-perimeter' : 'other-perimeter'"
					:data-contact="chip.contact ? '1' : '0'"
				/>
				<div
					v-for="other in others"
					:key="other.user"
					class="ophice-chip ophice-chip--remote absolute flex cursor-pointer items-center justify-center"
					:class="{ 'ophice-chip--lift': lifts[other.user] }"
					:style="chipStyle(other)"
					@click="openChatWith(other, $event)"
					:title="
						other.guest
							? __('Guest · {0}', [other.full_name])
							: other.offline
								? __('{0} (away, page closed)', [other.full_name])
								: other.full_name
					"
					data-testid="other-chip"
				>
					<span v-if="beams[other.user]" :key="beams[other.user]" class="ophice-beam" aria-hidden="true" />
					<span v-if="lifts[other.user]" :key="`shadow-${lifts[other.user]}`" class="ophice-lift-shadow" aria-hidden="true" />
					<span
						:key="`chip-${beams[other.user] || 0}-${lifts[other.user] || 0}`"
						class="inline-flex"
						:class="{ 'ophice-beam-drop': beams[other.user], 'ophice-lift': lifts[other.user] }"
						:style="{ '--chip-scale': chipScale, transform: `scale(${chipScale})` }"
					>
						<ChipFigure
							:user="other.user"
							:label="other.full_name"
							:image="other.user_image"
							:moving="Boolean(other.moving)"
							:offline="Boolean(other.offline)"
							:guest="Boolean(other.guest)"
							:area-hue="other.offline ? null : areaAt(other)?.color_hue"
							:badge="other.offline ? null : cockpitOf[other.user]"
						/>
					</span>
				</div>
				<!-- With the call (#2108) the bubble leaves the map: it sits on the stage where the user
				     last dragged it, and the map can move below it. -->
				<Teleport
					v-for="bubble in bubbleList"
					:key="bubble.user"
					to="#ophice-stage"
					:disabled="!isCallBubble(bubble)"
					defer
				>
					<EncounterBubble
						:ref="(el) => setBubbleRef(bubble.user, el)"
						:peer="bubble.peer"
						:me="me.user"
						:messages="bubble.messages"
						:loading="bubble.loading"
						:error="bubble.error"
						:sending="bubble.sending"
						:video="bubble.user === videoUser ? bubble.video : null"
						:display-name="me.full_name"
						:in-window="!!bubble.inWindow"
						:movable="isCallBubble(bubble)"
						:dragging="callDrag !== null"
						:video-width="isCallBubble(bubble) ? callLayout.videoW : 0"
						:me-chip="me"
						:style="{
							...(isCallBubble(bubble) ? callBubbleStyle() : bubbleStyle(bubble)),
							zIndex: zOf(`chat:${bubble.user}`),
						}"
						data-no-pan
						@pointerdown.capture="raise(`chat:${bubble.user}`)"
						@send="(text, done) => sendMessage(bubble, text, done)"
						@close="closeBubble(bubble.user)"
						@call="openEncounterCall(bubble)"
						@move-start="startCallDrag"
						@resize-start="startCallDrag"
					/>
				</Teleport>
				<div
					class="ophice-chip absolute flex cursor-pointer items-center justify-center"
					:class="{ 'ophice-chip--lift': lifts[me.user] }"
					:style="chipStyle(me)"
					:title="__('{0}: click to set your availability', [me.full_name])"
					data-testid="my-chip"
					@click="toggleStatus($event)"
				>
					<span v-if="beams[me.user]" :key="beams[me.user]" class="ophice-beam" aria-hidden="true" data-testid="beam" />
					<span v-if="lifts[me.user]" :key="`shadow-${lifts[me.user]}`" class="ophice-lift-shadow" aria-hidden="true" />
					<span
						:key="`chip-${beams[me.user] || 0}-${lifts[me.user] || 0}`"
						class="inline-flex"
						:class="{ 'ophice-beam-drop': beams[me.user], 'ophice-lift': lifts[me.user] }"
						:data-testid="lifts[me.user] ? 'my-chip-lifted' : undefined"
						:style="{ '--chip-scale': chipScale, transform: `scale(${chipScale})` }"
					>
						<ChipFigure
							:user="me.user"
							:label="me.full_name"
							:image="me.user_image"
							:area-hue="areaAt(me)?.color_hue"
							:badge="cockpitOf[me.user]"
							ring
							:moving="moving"
							:jumping="jumping"
							:double-jump="doubleJumped"
							:flying="flying"
						/>
					</span>
				</div>
				<!--
					Chat notices at their space (#2066): they pop up for a moment, then shrink to a small
					bubble on the space's top right corner; a click opens them again (PM, 2026-11-22).
					Burn notices next to my chip (#2057). Whatever was clicked last is in front.
				-->
				<template v-if="!meetingArea">
					<template v-for="notice in batchNoticeList" :key="`batch-${notice.name}`">
						<!--
							Space chat notices (#2066, #2091): only when there is something to decide (messages
							that will be deleted unless saved, or my Keep/Burn vote), as a small icon at the
							space's top right. A click opens the notice above the space (PM, 2026-11-22).
						-->
						<button
							type="button"
							class="ophice-notice-icon absolute flex items-center justify-center rounded-full text-ink-white shadow-lg"
							:class="[notice.vote_until && !notice.my_vote ? 'bg-amber-600' : 'bg-surface-red-5', { 'ophice-notice-icon--new': !seenIcons.has(noticeKey(notice)) }]"
							:style="iconAtArea(notice)"
							:title="notice.vote_until && !notice.my_vote ? __('Vote on the chat of {0}', [notice.area_title]) : __('The chat of {0} will be deleted unless someone saves it', [notice.area_title])"
							data-no-pan
							data-testid="notice-icon"
							@click.stop="toggleNotice(notice)"
						>
							<FeatherIcon :name="notice.vote_until && !notice.my_vote ? 'users' : 'message-square'" class="h-3 w-3" />
						</button>
						<div
							v-if="noticeOpen[notice.name]"
							class="ophice-notice absolute"
							data-no-pan
							:style="{ ...noticeAtArea(notice), zIndex: zOf(`batch:${notice.name}`) }"
							data-testid="notice-at-area"
							@pointerdown="raise(`batch:${notice.name}`)"
						>
							<BatchNotice
								:notice="notice"
								:now="clock"
								:busy="batchBusy[notice.name] || ''"
								@vote="(choice) => voteBatch(notice, choice)"
								@dismiss="dismissedBatches.add(notice.name)"
							/>
							<button
								type="button"
								class="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full border border-outline-gray-2 bg-surface-white text-ink-gray-6 shadow hover:text-ink-gray-9"
								:title="__('Close')"
								data-testid="notice-close"
								@click.stop="shrinkNotice(notice.name)"
							>
								<FeatherIcon name="x" class="h-3 w-3" />
							</button>
						</div>
					</template>
					<div
						v-if="noticeList.length"
						class="absolute flex flex-col gap-2"
						data-no-pan
						:style="{ ...noticeAtMe, zIndex: zOf('burn') }"
						data-testid="notice-at-me"
						@pointerdown="raise('burn')"
					>
						<BurnNotice
							v-for="notice in noticeList"
							:key="notice.encounter"
							:notice="notice"
							:now="now"
							:saving="notice.saving"
							@save="saveEncounter(notice)"
						/>
					</div>
				</template>
				<!-- Statuses float above their chips, under the chat bubbles. -->
				<StatusTag
					v-for="chip in statusChips"
					:key="`status-${chip.user}`"
					:status="chip.status"
					:now="clock"
					:style="tagStyle(chip)"
					:class="{ 'ophice-chip--remote': chip.user !== me.user, 'ophice-chip--lift': lifts[chip.user] }"
				/>
			</div>
				<!-- Adjust (#2089): the image's outline with move and resize handles, on top of everything. -->
				<BackgroundImage
					v-if="adjustingBackground && background && imageBox"
					frame
					:src="background"
					:placement="imageBox"
					:canvas="camera().canvas.value"
					:tile="tile"
					:ratio="backgroundRatio"
					@change="(place) => setLayout({ fit: false, ...place })"
				/>
			</div>
			<!-- A small map switches on a double click (#2091); a faint hint says so. -->
			<div
				v-if="inTiles"
				class="ophice-switch-hint pointer-events-none absolute inset-x-0 bottom-2 z-30 text-center"
				data-testid="map-switch-hint"
			>
				{{ mapBig ? SWITCH_BACK_HINT : SWITCH_HINT }}
			</div>
			<!-- Zoom (#2089): per person, remembered in this browser. -->
			<div
				class="ophice-zoom absolute z-30 flex items-center gap-0.5 rounded-lg border border-outline-gray-2 bg-surface-white/95 p-0.5 text-xs shadow"
				:class="meetingArea ? 'right-1.5 top-1.5' : 'bottom-3 left-3'"
				data-no-pan
				data-testid="map-zoom"
			>
				<button type="button" class="ophice-zoom__button" :title="__('Zoom out')" data-testid="zoom-out" @click="camera().zoomBy(1 / 1.25)">
					<FeatherIcon name="minus" class="h-3.5 w-3.5" />
				</button>
				<span class="w-10 text-center tabular-nums text-ink-gray-7" data-testid="zoom-level">{{ Math.round(camera().zoom.value * 100) }} %</span>
				<button type="button" class="ophice-zoom__button" :title="__('Zoom in')" data-testid="zoom-in" @click="camera().zoomBy(1.25)">
					<FeatherIcon name="plus" class="h-3.5 w-3.5" />
				</button>
				<button
					type="button"
					class="ophice-zoom__button px-1.5"
					:title="background && !meetingArea ? __('Show the whole image') : __('Show the whole grid')"
					data-testid="zoom-fit"
					@click="camera().fit(me.x, me.y)"
				>
					{{ __("Fit") }}
				</button>
			</div>
			</div>
			<div v-else-if="error" class="text-sm text-ink-red-4">{{ error }}</div>
		</div>
		<!-- Right sidebar (#2073, PM 2026-11-25): cockpits, my status and the testing settings; it
		     replaced the top bar. Part of the page like the people list, not floating over the map. -->
		<OphiceSidebar
			v-if="me"
			v-model:collapsed="sideCollapsed"
			:icon="OPHICE_ICON"
			:cockpits="barCockpits"
			:open-route="openRoute"
			:status="me.status"
			:status-open="statusOpen"
			:ui-scale="uiScale"
			:scales="UI_SCALES"
			:can-edit-map="canEditMap"
			:editing-areas="editingAreas"
			:adjusting-background="adjustingBackground"
			:has-background="Boolean(background)"
			:background-busy="backgroundBusy"
			:debug-options="debugOptions"
			@open="openCockpit"
			@status="toggleStatus()"
			@text-step="stepUiScale"
			@text-reset="setUiScale(1)"
			@areas="editingAreas = !editingAreas"
			@background="backgroundInput?.click()"
			@adjust="adjustingBackground = !adjustingBackground"
			@remove-background="removeBackground"
		/>
		</div>
		<!-- Over an open cockpit (#2074): the office small, with pings and quick replies. -->
		<MiniMap
			v-if="cockpitOpen && me"
			:cols="me.cols"
			:rows="me.rows"
			:me="me"
			:others="others"
			:areas="areas"
			:background="background"
			:background-layout="backgroundLayout"
			:background-ratio="backgroundRatio"
			:pings="pings"
			:notice-count="noticeList.length + batchNoticeList.length"
			:meeting="Boolean(meetingArea)"
			:float-target="pipBody"
			@slots="(slots) => (dockRects = slots)"
			@float="floatAll"
			@fullscreen="emit('back-to-map')"
			@reply="quickReply"
			@open-chat="openFromPing"
			@dismiss="(ping) => dropPing(ping.id)"
			@send="sendFromPing"
		/>
		<GuestInviteMenu
			v-if="guestInvite"
			:key="guestInvite.guest.user"
			:guest="guestInvite.guest"
			:at="guestInvite.at"
			@close="guestInvite = null"
		/>
		<ChatWithMenu v-if="chatWith" :key="chatWith.person.user" :person="chatWith.person" :at="chatWith.at" @close="chatWith = null" />
	</div>
</template>

<script setup>
import { computed, getCurrentInstance, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import ChipFigure from "../components/ChipFigure.vue"
import EncounterBubble from "../components/EncounterBubble.vue"
import BurnNotice from "../components/BurnNotice.vue"
import BatchNotice from "../components/BatchNotice.vue"
import OphiceSidebar from "../components/OphiceSidebar.vue"
import GuestChat from "../components/GuestChat.vue"
import GuestInviteMenu from "../components/GuestInviteMenu.vue"
import MiniMap from "../components/MiniMap.vue"
import MapFog from "../components/MapFog.vue"
import BackgroundImage from "../components/BackgroundImage.vue"
import { useMapCamera } from "../composables/useMapCamera.js"
import { imagePlacement } from "../utils/ophiceView.js"
import { myZone } from "../utils/ophiceTime.js"
import { canFloat, openFloatingWindow } from "../utils/pip.js"
import { dropSpotOutside } from "../utils/ophiceDrop.js"
import {
	CALL_DEFAULT,
	callBox,
	encounterCallWindowName,
	jitsiCallUrl,
	resizeCall,
} from "../utils/ophiceCall.js"
import MeetingHuddle from "../components/MeetingHuddle.vue"
import AreaLayer from "../components/AreaLayer.vue"
import AreaDialog from "../components/AreaDialog.vue"
import MeetingPanel from "../components/MeetingPanel.vue"
import AreaChat from "../components/AreaChat.vue"
import PeopleSidebar from "../components/PeopleSidebar.vue"
import ChatWithMenu from "../components/ChatWithMenu.vue"
import StatusTag from "../components/StatusTag.vue"
import StatusMenu from "../components/StatusMenu.vue"
import { __ } from "@spa/utils/i18n.js"
import { mountPhriend } from "@spa/phriend.js"
import router from "../router.js"

const props = defineProps({
	/** A cockpit is in front (#2073): the keyboard belongs to it, the chip stands still. */
	cockpitOpen: { type: Boolean, default: false },
	/** The cockpit loaded in the frame, e.g. "/sales-cockpit" (a dot in the shortcut bar). */
	openRoute: { type: String, default: "" },
})
const emit = defineEmits(["open-cockpit", "back-to-map"])
// Served by Frappe, not bundled.
const OPHICE_ICON = "/assets/phamos/manifest/ophice-icon-192.png"

// The cockpit someone is in (#2065), as a small icon on their chip (#2073): from the people
// list, so only for those who show their details.
const cockpitOf = computed(() => {
	const map = {}
	for (const person of people.value) {
		if (person.online && person.cockpit?.logo) map[person.user] = person.cockpit
	}
	return map
})

// The cockpits for the shortcut bar (#2073), Personal Cockpit first.
const cockpits = ref([])
async function loadCockpits() {
	try {
		cockpits.value = (await call(`${API}.get_cockpits`)) || []
	} catch {
		cockpits.value = []
	}
}

// A cockpit with its own space on the map is reached there, so it leaves the shortcut bar
// (PM, 2026-11-22). The full list stays: stopping in a space still checks it.
const barCockpits = computed(() => {
	const placed = new Set(areas.value.filter((a) => a.kind === "Cockpit" && a.cockpit).map((a) => a.cockpit))
	return cockpits.value.filter((c) => !placed.has(c.route))
})

// Positions are in tile units (floats): the grid is drawn, but movement is free.
const DIRECTIONS = {
	arrowup: [0, -1],
	w: [0, -1],
	arrowdown: [0, 1],
	s: [0, 1],
	arrowleft: [-1, 0],
	a: [-1, 0],
	arrowright: [1, 0],
	d: [1, 0],
}
const SPEED = 6.6 // tiles per second (10% up on 6, PM 2026-11-21)
const SHIFT_SPEED = 16.5
// Two chips can't overlap: centres stay at least this far apart (one chip is 0.8 tiles wide).
const MIN_DISTANCE = 0.8
const SAVE_AFTER_MS = 400
const ARROWS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
// A quick tap (pressed and released before the next frame) still moves this long.
const TAP_SECONDS = 0.05
// The avatar is drawn at 40px and scaled to the tile.
const AVATAR_PX = 40
// Presence (#2055): a heartbeat keeps my chip on everyone's grid; moves go out at most this often.
const HEARTBEAT_MS = 10000
const SEND_MOVE_EVERY_MS = 120
// Another chip's legs kick until this long after its last move arrived.
const REMOTE_MOVING_MS = 250
const API = "phamos.api.ophice"
// Spaces with a meeting (#2060, #2081): stop inside and you join it.
const MEETING_KINDS = ["Meeting", "Guest", "Customer meeting", "Cockpit"]
// Guest kinds have the guest chat (#2083); the others the area chat.
const GUEST_KINDS = ["Guest", "Customer meeting"]
// Encounters (#2056): closer than this (centres, tiles) opens the chat; farther than the second
// closes it again, so standing right at the edge does not flicker.
// Each chip's perimeter has half the encounter distance as radius: two touching circles = in range.
const ENCOUNTER_DISTANCE = 2
const PART_DISTANCE = 2.4
const PERIMETER_RADIUS = ENCOUNTER_DISTANCE / 2
const BUBBLE_WIDTH = 288

// The cockpit's realtime socket (as in useUserRealtime); without it Ophice still works alone.
const instance = getCurrentInstance()
const socket = instance?.appContext.config.globalProperties.$socket || inject("$socket", null)

const stage = ref(null)
const me = ref(null)
const others = ref([])
// Drives the kicking legs of my chip.
const moving = ref(false)
const error = ref("")
const view = reactive({ width: 0, height: 0, left: 0, top: 0 })

// The largest square tile that fits the whole grid into the page; in a meeting (#2061) into
// the mini map at the bottom left.
const MINI_SHARE = 0.3
const MINI_MIN = 260
const MINI_MAX = 440
const STAGE_PAD = 16
const miniWidth = computed(() => Math.max(MINI_MIN, Math.min(MINI_MAX, view.width * MINI_SHARE)))
// `tile` and the cameras are set up below, once the background settings exist (#2089).

// Where the meeting window sits, as shares of the stage (they follow the window size); the
// user's own placement is kept in this browser.
const MEETING_RECT_KEY = "phamos_ophice_meeting_rect"
function defaultMeetingRect() {
	const width = view.width || 1200
	const height = view.height || 800
	const left = miniWidth.value + STAGE_PAD * 2
	return {
		x: left / width,
		y: STAGE_PAD / height,
		w: (width - left - STAGE_PAD) / width,
		h: (height - STAGE_PAD * 2) / height,
	}
}
function storedMeetingRect() {
	try {
		const rect = JSON.parse(localStorage.getItem(MEETING_RECT_KEY) || "null")
		const ok = rect && ["x", "y", "w", "h"].every((k) => Number.isFinite(rect[k]) && rect[k] >= 0 && rect[k] <= 1)
		return ok ? rect : null
	} catch {
		return null
	}
}
const meetingRect = ref(storedMeetingRect())
const meetingPanel = ref(null)
function setMeetingRect(rect) {
	meetingRect.value = rect
	try {
		localStorage.setItem(MEETING_RECT_KEY, JSON.stringify(rect))
	} catch {
		// private window: the placement lasts until the reload
	}
}
const chipScale = computed(() => (tile.value * 0.8) / AVATAR_PX)

// The walkable grid inside the canvas: its tile (0,0) sits at the camera's origin.
const gridStyle = computed(() => ({
	left: `${camera().origin.value.x}px`,
	top: `${camera().origin.value.y}px`,
	width: `${tile.value * me.value.cols}px`,
	height: `${tile.value * me.value.rows}px`,
	"--tile": `${tile.value}px`,
}))
const canvasStyle = computed(() => ({
	width: `${camera().size.value.width}px`,
	height: `${camera().size.value.height}px`,
	transform: camera().transform.value,
}))
const viewportStyle = computed(() =>
	meetingArea.value
		? tileRects.value?.map
			? { ...rectStyle(tileRects.value.map), ...meetingFrameStyle.value }
			: { left: `${STAGE_PAD}px`, bottom: `${STAGE_PAD}px`, width: `${miniView.value.width}px`, height: `${miniView.value.height}px` }
		: {}
)

// Adjust panel (#2089): the image's place and width in tiles, nudged in half tiles.
const IMAGE_FIELDS = [
	{ key: "width", label: __("Width") },
	{ key: "left", label: __("Left") },
	{ key: "top", label: __("Top") },
]
const GRID_AXES = [
	{ key: "cols", label: __("Across") },
	{ key: "rows", label: __("Down") },
]
const gridBusy = ref(false)

function fmtTiles(value) {
	return Math.round((value || 0) * 100) / 100
}

/** Move the image (left/top) or change its width by `by` tiles; the width keeps the ratio. */
function nudgeImage(key, by) {
	const box = imageBox.value
	if (!box) return
	const next = { left: box.left, top: box.top, width: box.width }
	next[key] = Math.round((next[key] + by) * 1000) / 1000
	if (key === "width") next.width = Math.max(5, next.width)
	setLayout({ fit: false, ...next })
}

async function setGrid(cols, rows) {
	gridBusy.value = true
	try {
		const size = await call(`${API}.set_grid`, { cols, rows })
		me.value.cols = size.cols
		me.value.rows = size.rows
		moveTo(me.value.x, me.value.y)
	} catch (e) {
		toast.error(errorText(e) || __("The grid could not be changed."))
	} finally {
		gridBusy.value = false
	}
}

function changeGrid(key, by) {
	const size = { cols: me.value.cols, rows: me.value.rows }
	size[key] += by
	setGrid(size.cols, size.rows)
}

/** Grow the grid right and down until it covers the image (it starts at the grid's corner). */
function gridToImage() {
	const box = imageBox.value
	if (!box) return
	setGrid(Math.max(me.value.cols, Math.ceil(box.left + box.width)), Math.max(me.value.rows, Math.ceil(box.top + box.height)))
}

// Where the background lies, in grid tiles (null without one).
const backgroundRatio = ref(0)
const imageBox = computed(() =>
	background.value && me.value
		? imagePlacement(backgroundLayout.value, backgroundRatio.value, me.value.cols, me.value.rows)
		: null
)

/** A press on the map pans it (after a few px), unless a tool or a panel owns the press. */
function onViewportDown(event) {
	if (editingAreas.value || adjustingBackground.value) return
	if (event.target.closest?.("[data-no-pan], button, a, input, textarea, select")) return
	camera().onPointerDown(event)
}

/** A double click on the map in a meeting: the map big, or back to the standard view (#2091). */
function onViewportDblclick(event) {
	if (!inTiles.value || event.target.closest?.("[data-no-pan]")) return
	mapBig.value = !mapBig.value
	nextTick(() => me.value && miniCam.place(me.value.x, me.value.y))
}
// "Double-click to switch" on small maps; "double-tap" on touch screens.
const COARSE = window.matchMedia?.("(pointer: coarse)").matches
const SWITCH_HINT = COARSE ? __("Double-tap to switch") : __("Double-click to switch")
const SWITCH_BACK_HINT = COARSE ? __("Double-tap for the meeting view") : __("Double-click for the meeting view")

/** Scroll pans, Ctrl/⌘ + scroll zooms; not inside a scrolling panel (a chat) over the map. */
function onViewportWheel(event) {
	if (event.target.closest?.("[data-no-pan]") && !(event.ctrlKey || event.metaKey)) return
	event.preventDefault()
	camera().onWheel(event)
}

// --- Background image (one for everyone, anyone may change it).

const background = ref("")
const FITTED = { fit: true, left: 0, top: 0, width: 40, zoom: 1 }
const backgroundLayout = ref({ ...FITTED })

// The map's camera (#2089): the big map fills the stage, in a meeting the mini map sits at the
// bottom left; each has its own zoom, remembered in this browser.
const gridSize = () => ({ cols: me.value?.cols || 40, rows: me.value?.rows || 25 })
// --- Meeting view (#2061, #2091): fixed places. The chat top left, the map bottom left, the call
// big on the right. A double click on the map swaps it with the call (the map big), another one
// brings the standard view back (PM, 2026-11-22). The call's frame is never moved in the page
// (that would restart it): everything lies at fixed window px.
const mapBig = ref(false)
const inTiles = computed(() => Boolean(meetingArea.value && !props.cockpitOpen && !pipBody.value && view.width))
// The places themselves, without asking whether a meeting is on: the mini map's camera reads them
// while the page is still being set up.
const fixedPlaces = computed(() => {
	const { cols, rows } = gridSize()
	const pad = STAGE_PAD
	const leftW = miniWidth.value
	const mapH = Math.round(Math.min(view.height * 0.45, (leftW * rows) / cols))
	const at = (x, y, w, h) => ({ left: view.left + x, top: view.top + y, width: w, height: h })
	const small = at(pad, view.height - pad - mapH, leftW, mapH)
	const big = at(pad * 2 + leftW, pad, view.width - pad * 3 - leftW, view.height - pad * 2)
	return {
		chat: at(pad, pad, leftW, view.height - pad * 3 - mapH),
		map: mapBig.value ? big : small,
		video: mapBig.value ? small : big,
	}
})
const tileRects = computed(() => (inTiles.value ? fixedPlaces.value : null))
const rectStyle = (r) => ({ position: "fixed", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` })

// The map's tile in a meeting is its camera's view.
const miniView = computed(() => {
	const r = fixedPlaces.value.map
	return { width: Math.max(0, r.width), height: Math.max(0, r.height) }
})
const mainCam = useMapCamera({
	view,
	grid: gridSize,
	image: () => imageBox.value,
	// A new key (#2139): zooms remembered before counted from the whole grid, not the image.
	storageKey: "phamos_ophice_zoom_image",
	startZoom: () => backgroundLayout.value?.zoom || 1,
	minTile: 8,
	fitImage: true,
})
const miniCam = useMapCamera({
	view: () => miniView.value,
	grid: gridSize,
	image: () => imageBox.value,
	storageKey: "phamos_ophice_zoom_mini",
	pad: 0,
})
const camera = () => (meetingArea.value ? miniCam : mainCam)
const tile = computed(() => (me.value ? camera().tile.value : 0))
// The first time the map has a size: centre on my chip.
watch(
	() => mainCam.tile.value,
	(value) => value && me.value && !mainCam.isPlaced() && mainCam.place(me.value.x, me.value.y)
)
const adjustingBackground = ref(false)
// The map tools (spaces, background) are for map editors (#2071); the server checks it too.
const canEditMap = ref(false)
// Nothing here is sent to the others or changes my real position.
const debugOptions = [
	{ label: __("Simulate beam-in"), icon: "log-in", onClick: () => me.value && playBeam(me.value.user) },
	{
		// Shows on the mini map, so open a cockpit first (#2074).
		label: __("Simulate a ping"),
		icon: "bell",
		onClick: () => {
			const other = others.value.find((o) => !o.guest) || { user: "nobody@example.com", full_name: __("A colleague") }
			pingWalkUp(other)
			if (!props.cockpitOpen) toast({ title: __("Open a cockpit to see the ping on the mini map."), icon: "info" })
		},
	},
]
let layoutTimer = null

// Live for me while dragging; saved (and sent to everyone) a moment after the last change.
function setLayout(change) {
	const current = backgroundLayout.value
	if (change.fit) backgroundLayout.value = { ...FITTED, zoom: current.zoom || 1 }
	else if (change.fit === false) {
		// From "fit" to placed: start where the image lies now (covering the grid).
		const from = current.fit && imageBox.value ? imageBox.value : current
		backgroundLayout.value = { left: from.left, top: from.top, width: from.width, zoom: current.zoom || 1, ...change, fit: false }
	} else backgroundLayout.value = { ...current, ...change }
	clearTimeout(layoutTimer)
	layoutTimer = setTimeout(async () => {
		const { fit, left, top, width, zoom } = backgroundLayout.value
		try {
			await call(`${API}.set_background_layout`, { fit: fit ? 1 : 0, left, top, width, zoom })
		} catch (e) {
			toast.error(errorText(e) || __("The background could not be adjusted."))
		} finally {
			layoutTimer = null
		}
	}, 300)
}
const backgroundInput = ref(null)
const backgroundBusy = ref(false)

async function uploadBackground(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (!file) return
	backgroundBusy.value = true
	try {
		const form = new FormData()
		form.append("file", file, file.name)
		const response = await fetch(`/api/method/${API}.upload_background`, {
			method: "POST",
			body: form,
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		})
		const data = await response.json().catch(() => ({}))
		if (!response.ok) throw { messages: serverMessages(data) }
		background.value = data.message?.url || ""
	} catch (e) {
		toast.error(errorText(e) || __("The image could not be uploaded."))
	} finally {
		backgroundBusy.value = false
	}
}

async function removeBackground() {
	backgroundBusy.value = true
	try {
		await call(`${API}.remove_background`)
		background.value = ""
	} catch (e) {
		toast.error(errorText(e) || __("The background could not be removed."))
	} finally {
		backgroundBusy.value = false
	}
}

function serverMessages(data) {
	try {
		return JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message)
	} catch {
		return []
	}
}
// Every chip with its perimeter; "contact" when it touches another one (anyone's, so groups
// show as touching circles too).
const perimeterList = computed(() => {
	if (!me.value) return []
	const chips = [{ ...me.value, mine: true }, ...others.value.map((o) => ({ ...o, mine: false }))]
	return chips.map((chip) => ({
		user: chip.user,
		x: chip.x,
		y: chip.y,
		mine: chip.mine,
		contact: chips.some((o) => o.user !== chip.user && Math.hypot(o.x - chip.x, o.y - chip.y) < ENCOUNTER_DISTANCE),
	}))
})

function perimeterStyle(chip) {
	const size = PERIMETER_RADIUS * 2 * tile.value
	// Centred on the chip's tile centre.
	const offset = (0.5 - PERIMETER_RADIUS) * tile.value
	return {
		width: `${size}px`,
		height: `${size}px`,
		transform: `translate(${chip.x * tile.value + offset}px, ${chip.y * tile.value + offset}px)`,
	}
}

// Notices on the map (#2066): a card 320 px wide, kept inside the map.
const NOTICE_W = 320
const NOTICE_H = 110
function noticeBox(left, top, bottomEdge) {
	const width = tile.value * (me.value?.cols || 0)
	const height = tile.value * (me.value?.rows || 0)
	// Below the place; above it when there is no room below.
	const y = top + NOTICE_H > height ? Math.max(0, bottomEdge - NOTICE_H) : top
	return {
		left: `${Math.max(4, Math.min(width - NOTICE_W - 4, left))}px`,
		top: `${Math.max(4, y)}px`,
	}
}
// --- Which pop-up on the map is in front (PM, 2026-11-22): the one clicked or opened last.
// Chat bubbles, chat notices and burn notices share one order (z 21–39, below menus and dialogs).

const frontOrder = ref([])
function raise(key) {
	frontOrder.value = [...frontOrder.value.filter((k) => k !== key), key].slice(-18)
}
function zOf(key) {
	const index = frontOrder.value.indexOf(key)
	return index < 0 ? 20 : 21 + index
}

// Chat notices (#2091): a small icon at the space; a click opens the notice above it.
const noticeOpen = reactive({})
function openNotice(name) {
	noticeOpen[name] = true
	raise(`batch:${name}`)
}
function toggleNotice(notice) {
	seenIcons.add(noticeKey(notice))
	if (noticeOpen[notice.name]) shrinkNotice(notice.name)
	else openNotice(notice.name)
}
// An icon pulses until it was opened once per change (grace started, vote opened).
const seenIcons = reactive(new Set())
const noticeKey = (notice) => `${notice.name}:${notice.status}:${notice.vote_until || ""}`
function iconAtArea(notice) {
	const area = areas.value.find((a) => a.name === notice.area)
	if (!area) return { right: "8px", top: "8px", width: "22px", height: "22px", zIndex: 15 }
	const t = tile.value
	return {
		left: `${(area.x + area.width) * t - 11}px`,
		top: `${area.y * t - 11}px`,
		width: "22px",
		height: "22px",
		zIndex: 15,
	}
}
function shrinkNotice(name) {
	noticeOpen[name] = false
}

// Above its space; on it, at its top, when there is no room above (#2091).
function noticeAtArea(notice) {
	const area = areas.value.find((a) => a.name === notice.area)
	if (!area) return { right: "8px", top: "8px" }
	const t = tile.value
	const width = t * (me.value?.cols || 0)
	const left = (area.x + area.width / 2) * t - NOTICE_W / 2
	const above = area.y * t - NOTICE_H - 8
	return {
		left: `${Math.max(4, Math.min(width - NOTICE_W - 4, left))}px`,
		top: `${above >= 4 ? above : area.y * t + 6}px`,
	}
}
const noticeAtMe = computed(() => {
	if (!me.value) return {}
	const t = tile.value
	return noticeBox(me.value.x * t + t * 1.2, me.value.y * t - t * 0.5, me.value.y * t - 6)
})

function chipStyle(chip) {
	return {
		width: `${tile.value}px`,
		height: `${tile.value}px`,
		transform: `translate(${chip.x * tile.value}px, ${chip.y * tile.value}px)`,
	}
}

const held = new Set()
// Keys pressed since the last frame: they move once even if already released again.
const tapped = new Set()
let shift = false
let frame = null
let lastTime = 0
let saveTimer = null
let saved = null

function isTyping(target) {
	if (!target) return false
	const tag = target.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable
}

function onKeydown(event) {
	shift = event.shiftKey
	if (props.cockpitOpen) return
	// Cmd/Ctrl+F: find a person (#2091), instead of the browser's find while Ophice is in front.
	if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key?.toLowerCase() === "f" && me.value) {
		event.preventDefault()
		peopleSidebar.value?.openSearch()
		return
	}
	// Adjust (#2089): arrow keys move the image (1 px, with Shift half a tile), not the chip.
	if (adjustingBackground.value && imageBox.value && ARROWS[event.key] && !isTyping(event.target)) {
		event.preventDefault()
		const step = event.shiftKey ? 0.5 : 1 / (tile.value || 1)
		const [dx, dy] = ARROWS[event.key]
		const box = imageBox.value
		setLayout({ fit: false, left: Math.round((box.left + dx * step) * 1000) / 1000, top: Math.round((box.top + dy * step) * 1000) / 1000, width: box.width })
		return
	}
	if (!me.value || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return
	if (event.key === "Escape" && meetingArea.value && !Object.keys(bubbles).length && !document.fullscreenElement) {
		event.preventDefault()
		if (!meetingPanel.value?.exitFill()) leaveMeeting(true)
		return
	}
	if (!held.size && !event.repeat) {
		// Typed while the chat that just opened is still loading: keep it for the chat.
		if (bufferWhileOpening(event)) return
		// Esc said "walk on"; Enter brings the chat back while still next to the person.
		if (event.key === "Enter" && reopenDismissed()) {
			event.preventDefault()
			return
		}
	}
	// Space: jump, over other chips, so nobody gets stuck anywhere (PM, 2026-11-22). Again in
	// the air: double jump. Held until landing: hover with wings until it is let go.
	if (event.code === "Space") {
		event.preventDefault()
		spaceHeld = true
		if (event.repeat) return
		backFromStatus()
		// Moving my chip folds the people list back (#2091).
		peopleSidebar.value?.fold()
		if (!jump && !flying.value) startJump()
		else if (jump && !jump.doubled) doubleJump()
		return
	}
	const key = event.key.toLowerCase()
	if (!DIRECTIONS[key]) return
	event.preventDefault()
	backFromStatus()
	peopleSidebar.value?.fold()
	held.add(key)
	heldCount.value = held.size
	if (!event.repeat) tapped.add(key)
	if (!frame) {
		lastTime = performance.now()
		frame = requestAnimationFrame(tick)
	}
}

function onKeyup(event) {
	shift = event.shiftKey
	if (event.code === "Space") {
		spaceHeld = false
		if (flying.value) land()
		return
	}
	// With Shift held, "w" arrives as "W": lower-case both ways.
	const wasWalking = held.size > 0
	held.delete(event.key.toLowerCase())
	heldCount.value = held.size
	// Every key let go next to someone: the chat opens and has the keyboard (PM, 2026-11-21).
	// Whoever keeps a key held walks on, also when changing keys with overlap.
	if (wasWalking && !held.size && !flying.value && !jump) chatOnStop()
}

/** The nearest chip within the encounter distance, or null. */
function nearestInRange() {
	let best = null
	for (const other of others.value) {
		// Guests (#2082) talk in the guest area's chat and meeting, not in encounters.
		if (other.offline || other.guest) continue
		const distance = distanceTo(other)
		if (distance < ENCOUNTER_DISTANCE && (!best || distance < best.distance)) best = { other, distance }
	}
	return best?.other || null
}

/** Stopped walking: next to someone, the chat opens (or gets the keyboard if already open). */
function chatOnStop() {
	joinAreaIfInside()
	openCockpitSpace()
	const other = nearestInRange()
	if (!other || dismissed.has(other.user)) return
	const bubble = bubbles[other.user]
	if (!bubble) openBubble(other, { focus: true })
	else if (!bubble.loading) focusBubble(other.user)
	else bubble.focusOnOpen = true
}

function bufferWhileOpening(event) {
	const bubble = Object.values(bubbles).find((b) => b.loading && b.focusOnOpen)
	if (!bubble || event.key.length !== 1) return false
	event.preventDefault()
	bubble.pendingText += event.key
	return true
}

function reopenDismissed() {
	const other = nearestInRange()
	if (!other || !dismissed.has(other.user)) return false
	dismissed.delete(other.user)
	openBubble(other, { focus: true })
	return true
}

// Leaving the window drops every held key, or the chip would keep sailing.
function releaseAll() {
	held.clear()
	heldCount.value = 0
	tapped.clear()
	shift = false
	spaceHeld = false
	if (flying.value) land()
}

// --- Other chips: dummies from the site config and the people who have the page open (#2055).

let presenceTtlMs = 45000
const lastSeen = new Map()
const movingTimers = new Map()

// --- Beam-in (#2072): a column of light, the chip drops in. user -> start time while it plays.

const BEAM_MS = 1600
const beams = reactive({})

function playBeam(user) {
	const started = Date.now()
	beams[user] = started
	setTimeout(() => {
		if (beams[user] === started) delete beams[user]
	}, BEAM_MS)
}

// --- Lifted out of a meeting space (Leave, Esc): picked up, carried over the border, set down
// just outside. user -> start time while it plays; the others see it from the move's lift flag.

const LIFT_MS = 900
// The server's move limit counts per 5 seconds (MOVE_WINDOW in phamos/api/ophice.py).
const LIFT_RETRY_MS = 5000
const lifts = reactive({})
let lifting = false

function playLift(user) {
	const started = Date.now()
	lifts[user] = started
	setTimeout(() => {
		if (lifts[user] === started) delete lifts[user]
	}, LIFT_MS)
}

/** Set my chip down just outside the meeting space I left; it stays put when there is no room. */
function dropOut(area) {
	if (!me.value || areaAt(me.value)?.name !== area.name) return
	// Left in the middle of a jump or while hovering: back on the ground first, so other chips
	// count as obstacles again (blocked() ignores them in the air) and the jump doesn't go on.
	jump = null
	jumping.value = false
	doubleJumped.value = false
	flying.value = false
	spaceHeld = false
	const spot = dropSpotOutside(area, me.value, {
		cols: me.value.cols,
		rows: me.value.rows,
		isFree: (x, y) => !blocked(x, y),
		otherAreas: areas.value.filter((a) => a.name !== area.name && MEETING_KINDS.includes(a.kind || "Meeting")),
	})
	if (!spot) return
	// Keys held while it is carried do nothing: the chip is in a hand, not walking.
	held.clear()
	tapped.clear()
	lifting = true
	// The mini map grows back to the full map first; the carry starts once the chip stands at
	// its old spot on the full map, or it would fly in from where the mini map had it.
	nextTick(() =>
		requestAnimationFrame(() =>
			requestAnimationFrame(() => {
				setTimeout(() => (lifting = false), LIFT_MS)
				if (!me.value) return
				playLift(me.value.user)
				moveTo(spot.x, spot.y)
				clearTimeout(sendTimer)
				sendTimer = null
				lastSent = performance.now()
				sendLift(spot)
				scheduleSave()
				checkEncounters()
				leaveMeetingIfOutside()
			})
		)
	)
}

/**
 * Tell the others about the lift. Walking stays well under the server's move limit, but a lost
 * request would leave me standing in the meeting for them: one more try after the limit's window.
 */
function sendLift(spot, retry = true) {
	// Walked on meanwhile: the normal moves have told them already, an old spot would pull me back.
	const stillThere = () => me.value && round(me.value.x) === round(spot.x) && round(me.value.y) === round(spot.y)
	const again = () => retry && setTimeout(() => stillThere() && sendLift(spot, false), LIFT_RETRY_MS)
	call(`${API}.move`, { x: round(spot.x), y: round(spot.y), lift: 1 })
		.then((sent) => sent || again())
		.catch(again)
}

function upsertOther(chip) {
	if (!chip?.user || chip.user === me.value?.user) return
	if (chip.beam) playBeam(chip.user)
	lastSeen.set(chip.user, Date.now())
	const existing = others.value.find((o) => o.user === chip.user)
	// Away with the page closed (#2053): stays, greyed out; any heartbeat makes it live again.
	const values = { ...chip, offline: Boolean(chip.offline), status: chip.status || null }
	if (existing) Object.assign(existing, values)
	else others.value.push({ ...values, moving: false })
	checkEncounters()
}

const awayOver = (o) => !o.status?.until || Date.parse(o.status.until) + AWAY_GRACE_MS < Date.now()

function onRemoteMove(message) {
	const other = others.value.find((o) => o.user === message?.user)
	// A move from someone not on my grid yet (missed their join): ask for the full picture.
	if (!other) return message?.user && message.user !== me.value?.user ? refreshOthers() : null
	lastSeen.set(other.user, Date.now())
	// Only a lift that changes the place: a resent lift (its first answer got lost) plays once.
	if (message.lift && (other.x !== message.x || other.y !== message.y)) playLift(other.user)
	other.x = message.x
	other.y = message.y
	other.moving = true
	checkEncounters()
	noticeWalkUp(other)
	clearTimeout(movingTimers.get(other.user))
	movingTimers.set(
		other.user,
		setTimeout(() => (other.moving = false), REMOTE_MOVING_MS)
	)
}

function onRemoteLeave(message) {
	others.value = others.value.filter((o) => o.dummy || o.user !== message?.user)
	lastSeen.delete(message?.user)
	checkEncounters()
}

// Chips whose heartbeat stopped (tab killed, network gone) fade out after the presence TTL.
function pruneOthers() {
	const now = Date.now()
	others.value = others.value.filter((o) => {
		if (o.dummy || now - (lastSeen.get(o.user) || 0) < presenceTtlMs) return true
		// No heartbeat, but away: keep showing them, greyed out, until well after their return time.
		if (o.status?.kind === "away" && !awayOver(o)) return (o.offline = true)
		return false
	})
	checkEncounters()
}

async function refreshOthers() {
	try {
		const data = await call(`${API}.get_space`)
		for (const chip of data.others || []) upsertOther(chip)
	} catch {
		// The next heartbeat or event tries again.
	}
}

// --- Encounters (#2056): one bubble per chip I am standing next to.

const bubbles = reactive({})
const bubbleRefs = {}
// Chats closed with Esc stay closed until the two walk apart (or Enter opens them again).
const dismissed = new Set()
// The open encounter with each chip, also while its bubble is closed (Esc): parting needs it.
const encounterByUser = new Map()
const bubbleList = computed(() => Object.values(bubbles))

// Video (#2059): one call at a time, with the nearest person whose chat is open.
const videoUser = computed(() => {
	// One call at a time: an area's meeting wins over the encounter call (#2060).
	if (!me.value || meetingArea.value) return null
	let best = null
	for (const bubble of Object.values(bubbles)) {
		if (!bubble.video) continue
		const other = others.value.find((o) => o.user === bubble.user)
		if (!other) continue
		const distance = Math.hypot(other.x - me.value.x, other.y - me.value.y)
		if (!best || distance < best.distance) best = { user: bubble.user, distance }
	}
	return best?.user || null
})

// The encounter call in its own Jitsi window (#2108): bigger, and without the 5-minute cap of
// embedded meet.jit.si calls. The bubble then leaves its embedded call (no double join). The
// window stays open when the two walk apart: the call is the person's own from then on.
const callWindows = {}
function openEncounterCall(bubble) {
	const url = jitsiCallUrl(bubble.video, me.value?.full_name || "")
	if (!url) return
	const name = encounterCallWindowName(bubble.video)
	const open = callWindows[name]
	if (open && !open.closed) {
		open.focus()
		return
	}
	const win = window.open(url, name, "popup,width=1200,height=800")
	if (!win) {
		toast({ title: __("The browser blocked the new window. Please allow pop-ups for this site."), icon: "alert-circle" })
		return
	}
	// The call page must not steer Ophice's tab (reverse tabnabbing).
	try {
		win.opener = null
	} catch {
		// some browsers do not allow it
	}
	callWindows[name] = win
	bubble.inWindow = true
}

// The bubble with the embedded call (#2108): on the stage, where and how big this user last left
// it. Kept per browser and user, like the meeting window's place; the place as share of the free
// room, so it stays inside the stage at every window size. Default: centred at the top. The size
// rules (video between 16:9 and 1:1, chat at least 144px) are in callBox / resizeCall.
const CALL_POS_KEY = "phamos_ophice_call_pos"
const callPos = ref({ x: 0.5, y: 0, w: CALL_DEFAULT.w, h: CALL_DEFAULT.h })
const callDrag = ref(null)
function isCallBubble(bubble) {
	return bubble.user === videoUser.value && !!bubble.video && !bubble.inWindow
}
function callPosKey() {
	return `${CALL_POS_KEY}:${me.value?.user || ""}`
}
watch(
	() => me.value?.user,
	(user) => {
		if (!user) return
		try {
			const pos = JSON.parse(localStorage.getItem(callPosKey()) || "null")
			if (pos && [pos.x, pos.y].every((v) => Number.isFinite(v) && v >= 0 && v <= 1)) {
				callPos.value = {
					x: pos.x,
					y: pos.y,
					w: Number.isFinite(pos.w) ? pos.w : CALL_DEFAULT.w,
					h: Number.isFinite(pos.h) ? pos.h : CALL_DEFAULT.h,
				}
			}
		} catch {
			// private window: the default place
		}
	},
	{ immediate: true }
)
// Place and size as shown: px on the stage.
const callLayout = computed(() => {
	const box = callBox(callPos.value, view)
	const freeW = Math.max(0, view.width - box.w)
	const freeH = Math.max(0, view.height - box.h)
	return { ...box, left: callPos.value.x * freeW, top: callPos.value.y * freeH }
})
function callBubbleStyle() {
	const box = callLayout.value
	return { left: `${box.left}px`, top: `${box.top}px`, width: `${box.w}px`, height: `${box.h}px` }
}
function setCallBox({ left, top, w, h }) {
	const freeW = Math.max(0, view.width - w)
	const freeH = Math.max(0, view.height - h)
	left = Math.max(0, Math.min(freeW, left))
	top = Math.max(0, Math.min(freeH, top))
	callPos.value = { x: freeW ? left / freeW : 0.5, y: freeH ? top / freeH : 0, w, h }
}
// Moved by a press anywhere on it, resized by its edges and corners; the call's frame ignores the
// pointer meanwhile (else Jitsi takes the moves).
function startCallDrag(event, kind = "move") {
	if (event.button !== 0) return
	event.preventDefault()
	const { left, top, w, h } = callLayout.value
	callDrag.value = { kind, x: event.clientX, y: event.clientY, from: { left, top, w, h } }
	window.addEventListener("pointermove", moveCall)
	window.addEventListener("pointerup", stopCallDrag)
	window.addEventListener("pointercancel", stopCallDrag)
}
function moveCall(event) {
	const drag = callDrag.value
	if (!drag) return
	const dx = event.clientX - drag.x
	const dy = event.clientY - drag.y
	if (drag.kind === "move") setCallBox({ ...drag.from, left: drag.from.left + dx, top: drag.from.top + dy })
	else setCallBox(resizeCall(drag.from, drag.kind, dx, dy, view))
}
function stopCallDrag() {
	callDrag.value = null
	window.removeEventListener("pointermove", moveCall)
	window.removeEventListener("pointerup", stopCallDrag)
	window.removeEventListener("pointercancel", stopCallDrag)
	try {
		localStorage.setItem(callPosKey(), JSON.stringify(callPos.value))
	} catch {
		// private window: the place lasts until the reload
	}
}
// Ophice closed in the middle of a drag: no listeners left behind.
onBeforeUnmount(() => {
	if (callDrag.value) stopCallDrag()
})

function setBubbleRef(user, el) {
	if (el) bubbleRefs[user] = el
	else delete bubbleRefs[user]
}

function bubbleStyle(bubble) {
	const other = others.value.find((o) => o.user === bubble.user)
	if (!other || !me.value) return { display: "none" }
	const t = tile.value
	const gridWidth = t * me.value.cols
	const centreX = ((me.value.x + other.x) / 2 + 0.5) * t
	// Only the chat sits here; with the call the bubble is on the stage (callBubbleStyle, #2108).
	const width = BUBBLE_WIDTH
	const left = Math.max(width / 2 + 4, Math.min(gridWidth - width / 2 - 4, centreX))
	const top = Math.min(me.value.y, other.y)
	// Near the top edge the bubble hangs below the chips instead (their legs need ~0.5 tile).
	if (top * t < 270) {
		return { left: `${left}px`, top: `${(Math.max(me.value.y, other.y) + 1.6) * t}px`, transform: "translateX(-50%)" }
	}
	return { left: `${left}px`, top: `${(top - 0.1) * t}px`, transform: "translate(-50%, -100%)" }
}

function distanceTo(other) {
	return Math.hypot(other.x - me.value.x, other.y - me.value.y)
}

function checkEncounters() {
	if (!me.value) return
	for (const other of others.value) {
		const distance = distanceTo(other)
		// Chats don't open by walking past: they open when the keys are let go (chatOnStop) or
		// when the other person starts one (onEncounterStarted).
		if (distance > PART_DISTANCE) {
			delete bubbles[other.user]
			dismissed.delete(other.user)
			partFrom(other.user)
		}
	}
	// Someone who left the page also leaves the chat.
	for (const user of new Set([...Object.keys(bubbles), ...encounterByUser.keys()])) {
		if (!others.value.some((o) => o.user === user && !o.offline)) {
			delete bubbles[user]
			partFrom(user)
		}
	}
}

async function openBubble(other, { focus = false, fromPeer = false } = {}) {
	const bubble = reactive({
		pendingText: "",
		focusOnOpen: focus,
		user: other.user,
		peer: { user: other.user, full_name: other.full_name, user_image: other.user_image },
		encounter: null,
		messages: [],
		loading: true,
		error: "",
		sending: false,
	})
	bubbles[other.user] = bubble
	try {
		// The server checks that we really stand together: my latest spot goes first.
		await call(`${API}.move`, { x: round(me.value.x), y: round(me.value.y) })
		const data = await call(`${API}.open_encounter`, { with_user: other.user })
		bubble.encounter = data.encounter
		bubble.messages = data.messages || []
		bubble.video = data.video || null
		encounterByUser.set(other.user, data.encounter)
		// Met again before the chat burned: it goes on.
		delete notices[data.encounter]
	} catch (e) {
		bubble.error = errorText(e) || __("The chat could not be opened.")
	} finally {
		bubble.loading = false
	}
	if (!bubble.encounter || bubbles[other.user] !== bubble) return
	// Started here with a key: the chat has the keyboard. Started by the other person: only
	// if I'm standing; whoever is walking walks on.
	if (bubble.focusOnOpen || (fromPeer && !held.size)) focusBubble(other.user, bubble.pendingText)
	bubble.pendingText = ""
}

async function focusBubble(user, text = "") {
	await nextTick()
	if (!bubbles[user]?.encounter) return
	bubbleRefs[user]?.focus()
	if (text) bubbleRefs[user]?.insert(text)
}

// The other person started the chat (open_encounter tells this page): open it here too.
function onEncounterStarted(message) {
	const other = others.value.find((o) => o.user === message?.with)
	// In a cockpit (#2074): the mini map pings; the chat opens when I go back to the map.
	if (other && props.cockpitOpen) {
		pingWalkUp(other)
		return
	}
	if (!other || bubbles[other.user] || dismissed.has(other.user)) return
	if (distanceTo(other) > PART_DISTANCE) return
	openBubble(other, { fromPeer: true })
}

// How many movement keys are held (for templates that care whether the user walks).
const heldCount = ref(0)
// Esc: the chat closes and the keys move the chip again.
function closeBubble(user) {
	delete bubbles[user]
	dismissed.add(user)
	document.activeElement?.blur?.()
}

async function sendMessage(bubble, text, done) {
	if (!bubble.encounter) return
	bubble.sending = true
	try {
		addMessage(bubble, await call(`${API}.send_encounter_message`, { encounter: bubble.encounter, text }))
		done()
	} catch (e) {
		bubble.error = errorText(e) || __("The message could not be sent.")
	} finally {
		bubble.sending = false
	}
}

function addMessage(bubble, message) {
	if (message && !bubble.messages.some((m) => m.name === message.name)) bubble.messages.push(message)
}

function onEncounterMessage(payload) {
	const bubble = Object.values(bubbles).find((b) => b.encounter && b.encounter === payload?.encounter)
	if (bubble) addMessage(bubble, payload.message)
	const message = payload?.message
	if (props.cockpitOpen && message && message.owner !== me.value?.user) {
		addPing("message", __("{0}: {1}", [nameOf(message.owner), (message.text || "").slice(0, 80)]), { user: message.owner })
	}
}

// frappe-ui's call() puts the server's frappe.throw texts into error.messages.
function errorText(e) {
	const first = Array.isArray(e?.messages) ? e.messages[0] : ""
	if (!first || typeof first !== "string") return ""
	return new DOMParser().parseFromString(first, "text/html").body.textContent || ""
}

// --- Meeting areas (#2060).

const areas = ref([])
const editingAreas = ref(false)
const areaDraft = ref(null)
const meetingArea = ref(null)
// A meeting starts or ends (#2089): the map changes size; centre it on my chip.
watch(
	() => meetingArea.value?.name,
	(name) => !name && (mapBig.value = false)
)
watch(
	() => meetingArea.value?.name,
	() =>
		nextTick(() => {
			if (!me.value) return
			if (meetingArea.value) miniCam.place(me.value.x, me.value.y)
			else mainCam.place(me.value.x, me.value.y)
		})
)
// Left with Esc or "Leave": no rejoining until walking out of that area.
let meetingLeftHere = null

function areaAt(chip) {
	if (!chip) return null
	const cx = chip.x + 0.5
	const cy = chip.y + 0.5
	// Meeting spaces only: the start space (#2072) has no meeting, chat or glow.
	return (
		areas.value.find(
			(a) =>
				MEETING_KINDS.includes(a.kind || "Meeting") &&
				// A cockpit space only has a meeting when it has a link (#2076).
				(a.kind !== "Cockpit" || a.jitsi_room) &&
				cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height
		) || null
	)
}

// Who stands in which area, from the chips on the map (#2067): the sidebar groups and colours by it.
const areaOfUser = computed(() => {
	const map = {}
	for (const chip of [me.value, ...others.value]) {
		if (!chip || chip.offline) continue
		const area = areaAt(chip)
		if (area) map[chip.user] = area
	}
	return map
})

// The people standing in my meeting, from the map (live, unlike the people list): me first.
const huddle = computed(() => {
	const name = meetingArea.value?.name
	if (!name) return []
	return [me.value, ...others.value].filter((chip) => chip && areaOfUser.value[chip.user]?.name === name)
})

// --- Cockpit spaces (#2076): stop inside and its cockpit opens (once per visit to the space).

const autoCockpit = ref(true)
let cockpitSpaceHere = null

function cockpitSpaceAt(chip) {
	if (!chip) return null
	const cx = chip.x + 0.5
	const cy = chip.y + 0.5
	return areas.value.find((a) => a.kind === "Cockpit" && cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height) || null
}

function openCockpitSpace() {
	const space = cockpitSpaceAt(me.value)
	if (!space) {
		cockpitSpaceHere = null
		return
	}
	if (!autoCockpit.value || cockpitSpaceHere === space.name || props.cockpitOpen) return
	cockpitSpaceHere = space.name
	const cockpit = cockpits.value.find((c) => c.route === space.cockpit)
	if (cockpit) openCockpit(cockpit)
	else toast({ title: __("You can't open {0}; you can still use this space and its meeting.", [space.cockpit_title || space.cockpit]), icon: "info" })
}

/**
 * Open a cockpit (shortcut bar or cockpit space). Where the browser has it, the mini map goes
 * straight into its floating window, so it can be pulled out of the browser without a second click
 * (PM, 2026-11-22). The browser only allows that right after a click or key press; walking is key
 * presses, so stopping in a cockpit space still counts. Otherwise it stays over the cockpit.
 */
function openCockpit(cockpit) {
	if (canFloat && !pipBody.value && navigator.userActivation?.isActive) floatAll()
	emit("open-cockpit", cockpit)
}

async function setAutoCockpit(on) {
	autoCockpit.value = on
	try {
		await call(`${API}.set_auto_cockpit`, { on: on ? 1 : 0 })
	} catch {
		autoCockpit.value = !on
	}
}

function joinAreaIfInside() {
	const area = areaAt(me.value)
	if (!area || meetingArea.value?.name === area.name || meetingLeftHere === area.name) return
	meetingArea.value = area
}

function leaveMeetingIfOutside() {
	const here = areaAt(me.value)
	if (meetingLeftHere && here?.name !== meetingLeftHere) meetingLeftHere = null
	if (meetingArea.value && here?.name !== meetingArea.value.name) leaveMeeting(false)
}

function leaveMeeting(byChoice) {
	const left = meetingArea.value
	closeMeetingPip()
	// Leaving the space ends the call, also in its own window (PM, 2026-11-22).
	if (poppedOut.value) closeMeetingWindow()
	poppedOut.value = null
	if (byChoice && left) meetingLeftHere = left.name
	meetingArea.value = null
	// A "Not saved" chat burns once nobody is left in the area (#2062).
	if (left) call(`${API}.leave_area`, { area: left.name }).catch(() => {})
	// Left by choice while still standing inside: lifted out, so nobody sees me in the meeting.
	if (byChoice && left) dropOut(left)
}

// The space's colour around the meeting's people and chat (#2078), as around the meeting window.
const meetingFrameStyle = computed(() => {
	const h = meetingArea.value?.color_hue ?? 220
	return {
		border: `3px solid hsl(${h} 75% 50%)`,
		background: `hsl(${h} 75% 50% / 0.08)`,
		boxShadow: `0 0 18px 4px hsl(${h} 75% 50% / 0.4)`,
	}
})

// --- Guest chat (#2083) in guest and customer meeting areas: loaded when I step in, new messages
// arrive over realtime (the server tells everyone standing in the area).

const GUEST_API = "phamos.api.ophice_guest"
const guestChat = reactive({ area: "", messages: [] })

async function loadGuestChat(area) {
	guestChat.area = area.name
	guestChat.messages = []
	try {
		const data = await call(`${GUEST_API}.get_guest_chat`, { area: area.name })
		if (guestChat.area === area.name) guestChat.messages = data.messages || []
	} catch {
		// Not inside (yet): the next message or step brings it.
	}
}

function onGuestChat(payload) {
	if (payload?.area !== guestChat.area || !payload.message) return
	if (!guestChat.messages.some((m) => m.name === payload.message.name)) guestChat.messages.push(payload.message)
}

async function sendGuestChat(text) {
	const message = await call(`${GUEST_API}.send_guest_chat`, { area: meetingArea.value.name, text })
	onGuestChat({ area: guestChat.area, message })
}

watch(
	() => meetingArea.value?.name,
	() => {
		const area = meetingArea.value
		if (area && GUEST_KINDS.includes(area.kind)) loadGuestChat(area)
		else guestChat.area = ""
	}
)

// --- The meeting in its own browser window (#2078). meet.jit.si ends embedded calls after
// 5 minutes; opened directly it runs up to 95. Ophice then drops its own call (no double join).

const poppedOut = ref(null)
// Closed by hand (the x of that window): the person is out of the call until they open it again.
const meetingWindowClosed = ref(false)
let meetingWindow = null
let windowWatch = null

function popOut() {
	const area = meetingArea.value
	if (!area) return
	// Straight in, mic and camera on, my name filled in (#2108).
	const url = jitsiCallUrl({ domain: area.jitsi_domain, room: area.jitsi_room }, me.value?.full_name || "")
	if (!url) return
	if (meetingWindow && !meetingWindow.closed && poppedOut.value === area.name) {
		// Brings it to the front once; only picture-in-picture keeps a video in front.
		meetingWindow.focus()
		return
	}
	// Opened right over the meeting window, same size. After that it shows another site, and the
	// browser no longer lets Ophice move it.
	const at = meetingPanel.value?.screenRect?.()
	const place = at
		? `left=${at.left},top=${at.top},width=${Math.max(480, at.width)},height=${Math.max(360, at.height)}`
		: "width=1200,height=800"
	meetingWindow = window.open(url, `ophice-meeting-${area.name}`, `popup,${place}`)
	if (!meetingWindow) {
		toast({ title: __("The browser blocked the new window. Please allow pop-ups for this site."), icon: "alert-circle" })
		return
	}
	// The meeting page must not be able to steer Ophice's tab (reverse tabnabbing); Ophice keeps
	// its own handle to bring the window forward and close it.
	try {
		meetingWindow.opener = null
	} catch {
		// some browsers do not allow it; the window then keeps the link
	}
	poppedOut.value = area.name
	meetingWindowClosed.value = false
	clearInterval(windowWatch)
	windowWatch = setInterval(() => {
		if (meetingWindow?.closed) {
			meetingWindowClosed.value = true
			clearInterval(windowWatch)
		}
	}, 1000)
}

/** Close the meeting's own window, if Ophice opened it (lost after a reload of Ophice). */
function closeMeetingWindow() {
	clearInterval(windowWatch)
	try {
		meetingWindow?.close()
	} catch {
		// already gone
	}
	meetingWindow = null
	meetingWindowClosed.value = false
}

function bringBack() {
	closeMeetingWindow()
	poppedOut.value = null
}

// --- The meeting over an open cockpit (#2075): the same window and column, fixed to the browser
// window (bottom right by default, placement kept), or in a floating window on top of everything.

const viewport = reactive({ width: window.innerWidth, height: window.innerHeight })
function onViewportResize() {
	viewport.width = window.innerWidth
	viewport.height = window.innerHeight
}
window.addEventListener("resize", onViewportResize)
const FLOAT_RECT_KEY = "phamos_ophice_meeting_float_rect"
function defaultFloatRect() {
	const w = Math.min(460, viewport.width * 0.4)
	const h = Math.min(320, viewport.height * 0.45)
	return { x: (viewport.width - w - 16) / viewport.width, y: (viewport.height - h - 16) / viewport.height, w: w / viewport.width, h: h / viewport.height }
}
function storedFloatRect() {
	try {
		const rect = JSON.parse(localStorage.getItem(FLOAT_RECT_KEY) || "null")
		if (rect && ["x", "y", "w", "h"].every((k) => Number.isFinite(rect[k]) && rect[k] >= 0 && rect[k] <= 1)) return rect
	} catch {
		// private window
	}
	return null
}
const floatRectStored = ref(storedFloatRect())
const floatRect = computed(() => floatRectStored.value || defaultFloatRect())
function setFloatRect(rect) {
	floatRectStored.value = rect
	try {
		localStorage.setItem(FLOAT_RECT_KEY, JSON.stringify(rect))
	} catch {
		// private window: the placement lasts until the reload
	}
}
// People and chat to the left of the floating call, bottom-aligned with it.
const FLOAT_COLUMN_W = 320
const floatingColumnStyle = computed(() => {
	const r = floatRect.value
	const left = r.x * viewport.width
	const bottom = (r.y + r.h) * viewport.height
	const height = Math.min(440, viewport.height - 32)
	return {
		left: `${Math.max(8, left - FLOAT_COLUMN_W - 12)}px`,
		top: `${Math.max(8, bottom - height)}px`,
		width: `${FLOAT_COLUMN_W}px`,
		height: `${height}px`,
	}
})

// Where the call and chat sit inside the mini map (#2075): reported by the mini map.
const dockRects = ref(null)
function rectPx(rect) {
	return { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` }
}
watch(
	() => props.cockpitOpen,
	(open) => {
		if (open) return
		dockRects.value = null
		// Back in the office (PM, 2026-11-22): the floating window closes and call and chat come
		// back onto the map. A meeting in its own browser window (the long one, #2078) stays there.
		if (pipBody.value) closeMeetingPip()
	}
)

const pipBody = ref(null)
/** From the mini map: the map, and in a meeting the call and chat with it, in one floating window. */
async function floatAll() {
	pipBody.value = await openFloatingWindow({
		width: meetingArea.value ? 420 : 320,
		height: meetingArea.value ? 760 : 440,
		onClose: () => (pipBody.value = null),
	})
}
async function floatMeeting() {
	// The call moves into the floating window: Jitsi joins again there (an iframe that moves restarts).
	pipBody.value = await openFloatingWindow({
		width: 480,
		height: 760,
		onClose: () => (pipBody.value = null),
	})
}
function closeMeetingPip() {
	pipBody.value?.ownerDocument?.defaultView?.close()
	pipBody.value = null
}

// Left column of the meeting view: the area chat fills it down to the mini map.
// The chat (with the people of the meeting) in its tile (#2091).
const areaChatStyle = computed(() => (tileRects.value?.chat ? rectStyle(tileRects.value.chat) : {}))

// --- People list (#2063) and "chat with" (list or map).

const PEOPLE_KEY = "phamos_ophice_people_open"
const SIDEBAR_KEY = "phamos_ophice_sidebar_open"
const PEOPLE_REFRESH_MS = 15000
const people = ref([])
const hideDetails = ref(false)
const chatWith = ref(null)
// Inviting a guest to a customer meeting (#2084): { guest, at }.
const guestInvite = ref(null)
// --- Text size (#2091): scales Ophice's text and controls (they are in rem) and the cockpit inside
// Ophice; not the map, which has its own zoom (#2089). Remembered in this browser.
const UI_SCALES = [0.85, 0.9, 1, 1.1, 1.25, 1.4, 1.6]
const UI_SCALE_KEY = "phamos_ophice_text_size"
const BASE_FONT_PX = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
function readUiScale() {
	try {
		const value = parseFloat(localStorage.getItem(UI_SCALE_KEY))
		return UI_SCALES.includes(value) ? value : 1
	} catch {
		return 1
	}
}
const uiScale = ref(readUiScale())
function setUiScale(value) {
	uiScale.value = value
	try {
		localStorage.setItem(UI_SCALE_KEY, String(value))
	} catch {
		// private window: back to normal after a reload
	}
}
function stepUiScale(by) {
	const index = UI_SCALES.indexOf(uiScale.value)
	setUiScale(UI_SCALES[Math.max(0, Math.min(UI_SCALES.length - 1, (index < 0 ? 2 : index) + by))])
}
watch(
	uiScale,
	(value) => {
		document.documentElement.style.fontSize = value === 1 ? "" : `${BASE_FONT_PX * value}px`
		// The cockpit in Ophice's frame follows (App.vue / CockpitFrame.vue listen).
		window.dispatchEvent(new CustomEvent("ophice-text-size", { detail: value }))
	},
	{ immediate: true }
)

// Kept open (#2091); folded to the chips by default.
const showPeople = ref(readFlag(PEOPLE_KEY, false))
const peopleSidebar = ref(null)
let peopleTimer = null
let peopleSoon = null

function readFlag(key, fallback) {
	try {
		const value = localStorage.getItem(key)
		return value === null ? fallback : value === "1"
	} catch {
		return fallback
	}
}

// The right sidebar (PM, 2026-11-25): folded to icons by default, remembered in this browser.
const sideCollapsed = ref(!readFlag(SIDEBAR_KEY, false))
watch(sideCollapsed, (value) => {
	try {
		localStorage.setItem(SIDEBAR_KEY, value ? "0" : "1")
	} catch {
		// private window: folded again after a reload
	}
})

/** Keep the people list open, or fold it back to its chips (#2091). */
function setPeoplePinned(value) {
	showPeople.value = Boolean(value)
	try {
		localStorage.setItem(PEOPLE_KEY, showPeople.value ? "1" : "0")
	} catch {
		// private window: back to the default after a reload
	}
}

// The strip shows everyone too (#2091), so the list is always loaded.
async function loadPeople() {
	if (!me.value) return
	try {
		const data = await call(`${API}.get_people`)
		people.value = data.people || []
		hideDetails.value = Boolean(data.hide_details)
	} catch {
		// the next round tries again
	}
}

/** Someone came, went, moved into an area or set a status: refresh soon, once. */
function peopleChanged() {
	clearTimeout(peopleSoon)
	peopleSoon = setTimeout(loadPeople, 1500)
}

async function setHideDetails(hide) {
	hideDetails.value = hide
	try {
		await call(`${API}.set_hide_details`, { hide: hide ? 1 : 0 })
	} catch (e) {
		hideDetails.value = !hide
		toast.error(errorText(e) || __("The setting could not be saved."))
	}
	loadPeople()
}

function openChatWith(person, event) {
	if (!person?.user || person.user === me.value?.user) return
	// A guest (#2082): no Raven; they can be invited to a customer meeting (#2084).
	if (person.guest) {
		guestInvite.value = { guest: person, at: { x: event?.clientX ?? 200, y: event?.clientY ?? 200 } }
		return
	}
	// A chip on the map: the list knows more (what they work on).
	const known = people.value.find((p) => p.user === person.user)
	chatWith.value = { person: known || person, at: { x: event?.clientX ?? 200, y: event?.clientY ?? 200 } }
}

function nameOf(user) {
	if (user === me.value?.user) return me.value.full_name
	return others.value.find((o) => o.user === user)?.full_name || user
}

function setAreas(list) {
	areas.value = list || []
	// The area I am meeting in was changed or deleted by someone.
	if (meetingArea.value) {
		const same = areas.value.find((a) => a.name === meetingArea.value.name)
		if (!same || same.jitsi_room !== meetingArea.value.jitsi_room || same.jitsi_domain !== meetingArea.value.jitsi_domain) {
			meetingArea.value = null
		} else meetingArea.value = same
	}
}

async function saveArea(values) {
	try {
		await call(`${API}.save_area`, {
			name: values.name || null,
			title: values.title,
			meeting_url: values.meeting_url,
			x: values.x,
			y: values.y,
			width: values.width,
			height: values.height,
			chat_mode: values.chat_mode || "Saved",
			kind: values.kind || "Meeting",
			cockpit: values.cockpit || "",
		})
	} catch (e) {
		throw new Error(errorText(e) || __("The area could not be saved."))
	}
}

/** An area dragged to a new place or size in edit mode: saved at once, for everyone. */
async function reshapeArea(area, rect) {
	try {
		await saveArea({ ...area, ...rect })
	} catch (e) {
		// The server refused (for example an overlap): the area stays where it was.
		toast({ title: e.message, icon: "alert-circle" })
	}
}

async function deleteArea(area) {
	try {
		await call(`${API}.delete_area`, { name: area.name })
	} catch (e) {
		throw new Error(errorText(e) || __("The area could not be deleted."))
	}
}

// --- Burn notices (#2057).

const notices = reactive({})
const noticeList = computed(() => Object.values(notices))
const now = ref(Date.now())
let nowTimer = null

// --- Status (#2053): be right back / away with a note and a return time.

const AWAY_GRACE_MS = 3600 * 1000
const statusOpen = ref(false)
// Where the status menu opens: next to my chip when I click it, else under the header button.
const statusAt = ref(null)
const statusMenuStyle = computed(() => ({
	left: `${Math.max(8, Math.min(window.innerWidth - 336, statusAt.value.x + 12))}px`,
	top: `${Math.max(8, Math.min(window.innerHeight - 380, statusAt.value.y + 12))}px`,
}))

function toggleStatus(event) {
	if (statusOpen.value) {
		statusOpen.value = false
		return
	}
	statusAt.value = event ? { x: event.clientX, y: event.clientY } : null
	statusOpen.value = true
}
// For "back in 20 minutes": a slow clock is enough.
const clock = ref(Date.now())
const clockTimer = setInterval(() => (clock.value = Date.now()), 30000)
let statusClearing = false

const statusChips = computed(() => {
	if (!me.value) return []
	return [me.value, ...others.value].filter((chip) => chip.status)
})

function tagStyle(chip) {
	// Above the chip, clear of its ring; towards the map's edges the tag shifts inwards (the tail
	// keeps pointing at the chip), so it is never cut off.
	const share = Math.round(10 + (80 * chip.x) / Math.max(1, me.value.cols - 1))
	return {
		left: "0px",
		top: "0px",
		"--tail": `${share}%`,
		transform: `translate(${(chip.x + 0.5) * tile.value}px, ${(chip.y - 0.12) * tile.value}px) translate(-${share}%, -100%)`,
	}
}

async function saveStatus(values) {
	try {
		me.value.status = await call(`${API}.set_status`, values)
	} catch (e) {
		throw new Error(errorText(e) || __("The status could not be set."))
	}
}

/** Moving means I'm back: the status goes. */
function backFromStatus() {
	if (!me.value?.status || statusClearing) return
	statusClearing = true
	me.value.status = null
	call(`${API}.set_status`, { kind: "" })
		.catch(() => {})
		.finally(() => (statusClearing = false))
}

function onRemoteStatus(message) {
	if (!message?.user) return
	if (message.user === me.value?.user) {
		// Set in another tab of mine.
		me.value.status = message.status || null
		return
	}
	const other = others.value.find((o) => o.user === message.user)
	if (!other) return
	other.status = message.status || null
	if (other.offline && !other.status) others.value = others.value.filter((o) => o !== other)
}

function partFrom(user) {
	const encounter = encounterByUser.get(user)
	if (!encounter) return
	encounterByUser.delete(user)
	call(`${API}.part_encounter`, { encounter })
		.then((notice) => notice && upsertNotice(notice))
		.catch(() => {})
}

function upsertNotice(notice) {
	if (!notice?.encounter) return
	const existing = notices[notice.encounter]
	if (existing?.state) return // already saved or burned
	const fields = {
		encounter: notice.encounter,
		with: notice.with,
		full_name: notice.full_name,
		user_image: notice.user_image,
		deadline: Date.now() + notice.burn_in * 1000,
		total: 60,
		saved_by_me: notice.saved_by_me,
		saved_by_peer: notice.saved_by_peer,
	}
	if (existing) Object.assign(existing, fields)
	else notices[notice.encounter] = reactive({ ...fields, state: "", saving: false, burnAsked: false })
	startClock()
}

function finishNotice(encounter, state) {
	const notice = notices[encounter]
	for (const [user, open] of encounterByUser) if (open === encounter) encounterByUser.delete(user)
	for (const bubble of Object.values(bubbles)) if (bubble.encounter === encounter) delete bubbles[bubble.user]
	if (!notice) return
	notice.state = state
	setTimeout(() => delete notices[encounter], state === "saved" ? 5000 : 4000)
}

async function saveEncounter(notice) {
	notice.saving = true
	try {
		const result = await call(`${API}.save_encounter`, { encounter: notice.encounter })
		notice.saved_by_me = true
		if (result?.saved) finishNotice(notice.encounter, "saved")
	} catch (e) {
		toast.error(errorText(e) || __("The chat could not be saved."))
	} finally {
		notice.saving = false
	}
}

// The countdown: at zero the page asks the server to burn (the scheduler does it for closed tabs).
function startClock() {
	if (nowTimer) return
	nowTimer = setInterval(() => {
		now.value = Date.now()
		for (const notice of Object.values(notices)) {
			if (!notice.state && !notice.burnAsked && notice.deadline <= now.value) {
				notice.burnAsked = true
				call(`${API}.burn_if_due`, { encounter: notice.encounter })
					.then((r) => r?.burned && finishNotice(notice.encounter, "burned"))
					.catch(() => {})
			}
		}
		if (!Object.keys(notices).length) {
			clearInterval(nowTimer)
			nowTimer = null
		}
	}, 250)
}

// --- Meeting chats waiting for me elsewhere on the map (#2066): grace time or a vote.

const batchNotices = ref([])
const batchBusy = reactive({})
const dismissedBatches = reactive(new Set())
// The area I'm in shows its batches in its own chat; the rest come here.
const batchNoticeList = computed(() =>
	batchNotices.value.filter((n) => n.area !== meetingArea.value?.name && !dismissedBatches.has(n.name))
)

async function loadBatchNotices() {
	try {
		const rows = await call(`${API}.get_batch_notices`)
		const loadedAt = Date.now()
		batchNotices.value = (rows || []).map((row) => ({ ...row, loadedAt }))
	} catch {
		// Not critical: the next change brings them.
	}
}

let batchNoticeTimer = null
function onAreaBatches() {
	clearTimeout(batchNoticeTimer)
	batchNoticeTimer = setTimeout(loadBatchNotices, 300)
}

async function voteBatch(notice, choice) {
	batchBusy[notice.name] = choice
	try {
		await call(`${API}.vote_batch`, { batch: notice.name, vote: choice })
		if (choice === "Keep" && !notice.vote_until) dismissedBatches.add(notice.name)
	} catch (e) {
		toast({ title: e?.messages?.[0] || __("Your vote could not be saved."), icon: "alert-circle" })
	} finally {
		delete batchBusy[notice.name]
		loadBatchNotices()
	}
}

const NOTICE_EVENTS = [
	[
		"ophice_guest_invite_answer",
		(m) =>
			toast({
				title: m?.accepted
					? __("{0} accepted and is on the way to {1}.", [m.guest, m.area_title])
					: __("{0} declined the invite to {1}.", [m.guest, m.area_title]),
				icon: m?.accepted ? "check" : "x",
			}),
	],
	["ophice_guest_chat", (payload) => onGuestChat(payload)],
	["ophice_area_batches", onAreaBatches],
	["ophice_burn_notice", upsertNotice],
	["ophice_save_vote", upsertNotice],
	["ophice_burn_cancel", (m) => delete notices[m?.encounter]],
	["ophice_saved", (m) => finishNotice(m?.encounter, "saved")],
	["ophice_burned", (m) => finishNotice(m?.encounter, "burned")],
]

// --- My presence.

let lastSent = 0
let sendTimer = null

function sendMove() {
	clearTimeout(sendTimer)
	sendTimer = null
	lastSent = performance.now()
	if (!me.value) return
	call(`${API}.move`, { x: round(me.value.x), y: round(me.value.y) }).catch(() => {})
}

// Leading and trailing: the first step goes out at once, the final spot always arrives.
function queueMove() {
	const wait = SEND_MOVE_EVERY_MS - (performance.now() - lastSent)
	if (wait <= 0) sendMove()
	else if (!sendTimer) sendTimer = setTimeout(sendMove, wait)
}

function heartbeat() {
	if (!me.value) return
	call(`${API}.heartbeat`, { x: round(me.value.x), y: round(me.value.y) }).catch(() => {})
	pruneOthers()
}

// On tab close the component never unmounts: tell the server with a request that outlives the page.
function leaveOnPagehide() {
	// Ophice closes: the call in its own window ends with it.
	if (poppedOut.value) closeMeetingWindow()
	try {
		fetch(`/api/method/${API}.leave`, {
			method: "POST",
			keepalive: true,
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		})
	} catch {
		// The presence TTL removes the chip anyway.
	}
}

// --- Pings on the mini map (#2074), while a cockpit is open.

const pings = ref([])
const nearMe = new Set()
let pingId = 0
const MAX_PINGS = 6

function addPing(kind, text, extra = {}) {
	// One ping per person and kind: the newest replaces the older one.
	const rest = pings.value.filter((p) => !(extra.user && p.user === extra.user && p.kind === kind))
	const ping = reactive({ id: ++pingId, kind, text, fresh: true, ...extra })
	pings.value = [ping, ...rest].slice(0, MAX_PINGS)
	setTimeout(() => (ping.fresh = false), 2500)
}

function dropPing(id) {
	pings.value = pings.value.filter((p) => p.id !== id)
}

function pingWalkUp(other) {
	addPing("walkup", __("{0} came over to you.", [other.full_name]), { user: other.user, name: other.full_name })
}

/** Someone stops next to my chip while I work in a cockpit. */
function noticeWalkUp(other) {
	if (!props.cockpitOpen || other.guest || other.offline || !me.value) return
	const near = distanceTo(other) < ENCOUNTER_DISTANCE
	if (near && !nearMe.has(other.user)) pingWalkUp(other)
	if (near) nearMe.add(other.user)
	else nearMe.delete(other.user)
}

function onMeetingMessage(payload) {
	const message = payload?.message
	if (!props.cockpitOpen || !meetingArea.value || payload?.area !== meetingArea.value.name) return
	if (!message || message.owner === me.value?.user) return
	const who = message.author || nameOf(message.owner)
	addPing("meeting", __("{0} in {1}: {2}", [who, meetingArea.value.title, (message.text || "").slice(0, 80)]))
}

// "I'll get back to you in x minutes": my status says so (everyone sees it above my chip), the
// chat with that person gets the line, and I get a reminder when the time is up.
const reminders = new Map()
async function quickReply(ping, minutes) {
	const note = __("I'll get back to you in {0} min", [minutes])
	// The status carries the time, so the bubble above my chip counts down (PM, 2026-11-22).
	const until = new Date(Date.now() + minutes * 60000).toISOString().replace(/\.\d{3}Z$/, "Z")
	try {
		await saveStatus({ kind: "brb", note: __("I'll get back to you"), until, tz: myZone() })
	} catch (e) {
		toast({ title: e.message, icon: "alert-circle" })
		return
	}
	const bubble = bubbles[ping.user]
	if (bubble?.encounter) sendMessage(bubble, note, () => {})
	dropPing(ping.id)
	clearTimeout(reminders.get(ping.user))
	reminders.set(
		ping.user,
		setTimeout(() => {
			reminders.delete(ping.user)
			const text = __("Time to get back to {0}.", [ping.name || nameOf(ping.user)])
			toast({ title: text, icon: "clock" })
			if (props.cockpitOpen) addPing("reminder", text, { user: ping.user })
		}, minutes * 60000)
	)
}

/** A reply typed in a ping, sent without leaving the cockpit: into the chat with that person, or
 *  into the chat of the meeting I stand in. */
async function sendFromPing(ping, text, done) {
	try {
		if (ping.kind === "meeting") {
			const area = meetingArea.value
			if (!area) throw new Error(__("You are no longer in the meeting."))
			if (!GUEST_KINDS.includes(area.kind)) await call(`${API}.send_area_message`, { area: area.name, text })
			else await sendGuestChat(text)
		} else {
			const other = others.value.find((o) => o.user === ping.user)
			if (!other) throw new Error(__("{0} has left.", [ping.name || nameOf(ping.user)]))
			if (!bubbles[other.user]?.encounter) await openBubble(other)
			const bubble = bubbles[other.user]
			if (!bubble?.encounter) throw new Error(bubble?.error || __("The chat could not be opened."))
			addMessage(bubble, await call(`${API}.send_encounter_message`, { encounter: bubble.encounter, text }))
		}
		ping.replies = [...(ping.replies || []), text]
		done(true)
	} catch (e) {
		toast({ title: errorText(e) || e.message || __("The message could not be sent."), icon: "alert-circle" })
		done(false)
	}
}

/** From a ping: back to the map; the chat with that person opens if they are still there. */
function openFromPing(ping) {
	dropPing(ping.id)
	emit("back-to-map")
	const other = others.value.find((o) => o.user === ping.user)
	if (!other) return
	nextTick(() => {
		if (bubbles[other.user]) focusBubble(other.user)
		else if (distanceTo(other) < PART_DISTANCE) openBubble(other, { focus: true })
	})
}

// Back on the map: the pings are seen.
watch(
	() => props.cockpitOpen,
	(open) => {
		if (!open) pings.value = []
		nearMe.clear()
	}
)

const round = (value) => Math.round(value * 100) / 100

const SOCKET_EVENTS = [
	["ophice_area_message", onMeetingMessage],
	["ophice_guest_chat", onMeetingMessage],
	["ophice_presence", upsertOther],
	["ophice_move", onRemoteMove],
	["ophice_leave", onRemoteLeave],
	["ophice_message", onEncounterMessage],
	["ophice_encounter_started", onEncounterStarted],
	["ophice_areas", (message) => setAreas(message?.areas)],
	["ophice_status", (message) => (onRemoteStatus(message), peopleChanged())],
	["ophice_leave", peopleChanged],
	["ophice_encounter_started", peopleChanged],
	[
		"ophice_background",
		(message) => {
			background.value = message?.url || ""
			// Not while I'm dragging the sliders myself (my own echo would jump back).
			if (!layoutTimer) backgroundLayout.value = message?.layout || { ...FITTED }
			if (message?.ratio) backgroundRatio.value = message.ratio
			if (!background.value) adjustingBackground.value = false
		},
	],
	// The grid grew or shrank (#2089): the same for everyone, my chip stays on it.
	[
		"ophice_grid",
		(message) => {
			if (!me.value || !message?.cols) return
			me.value.cols = message.cols
			me.value.rows = message.rows
			moveTo(me.value.x, me.value.y)
		},
	],
	...NOTICE_EVENTS,
	// Rejoin after a lost connection: the others may have moved meanwhile.
	["connect", () => (heartbeat(), refreshOthers())],
]

function blocked(x, y) {
	// In the air nothing blocks: that is the point of jumping.
	if (jump || flying.value) return false
	return others.value.some((o) => !o.offline && Math.hypot(o.x - x, o.y - y) < MIN_DISTANCE)
}

// --- Jump (Space): a short hop forward that passes over other chips.

const JUMP_MS = 420
const JUMP_DISTANCE = 2 // tiles, in the direction walked (or last walked)
const jumping = ref(false)
const doubleJumped = ref(false)
// Space still held when the jump lands: hovering with wings, over everyone, until it's let go.
const flying = ref(false)
let spaceHeld = false
let jump = null // { dir: [x, y], left: tiles still to cover, doubled }
let lastDir = [1, 0]

function startJump() {
	if (jump || lifting || !me.value) return
	jump = { dir: lastDir, left: JUMP_DISTANCE, doubled: false }
	jumping.value = true
	doubleJumped.value = false
	if (!frame) {
		lastTime = performance.now()
		frame = requestAnimationFrame(tick)
	}
}

/** Space again in the air: a second hop, as far again, from where the chip is now. */
function doubleJump() {
	jump.left += JUMP_DISTANCE
	jump.doubled = true
	doubleJumped.value = true
}

/** Back on the ground: slide on until no chip is underneath, then as after a walk. */
function land(dir = lastDir) {
	flying.value = false
	// Landed on someone: a little further along, up to 3 tiles.
	for (let extra = 0; extra <= 3 && blocked(me.value.x, me.value.y); extra += 0.1) {
		moveTo(me.value.x + dir[0] * 0.1, me.value.y + dir[1] * 0.1)
	}
	scheduleSave()
	queueMove()
	checkEncounters()
	leaveMeetingIfOutside()
	if (!held.size) chatOnStop()
}

/** The jump's share of this frame's movement; then hover (Space held) or land. */
function jumpStep(dt) {
	const step = Math.min(jump.left, (JUMP_DISTANCE * dt * 1000) / JUMP_MS)
	jump.left -= step
	const [dx, dy] = jump.dir
	moveTo(me.value.x + dx * step, me.value.y + dy * step)
	if (jump.left > 1e-6) return
	const dir = jump.dir
	jump = null
	jumping.value = false
	doubleJumped.value = false
	if (spaceHeld) flying.value = true
	else land(dir)
}

function moveTo(x, y) {
	me.value.x = Math.max(0, Math.min(me.value.cols - 1, x))
	me.value.y = Math.max(0, Math.min(me.value.rows - 1, y))
}

function tick(now) {
	let dt = Math.min(0.05, (now - lastTime) / 1000)
	lastTime = now
	const keys = new Set([...held, ...tapped])
	// Only taps this frame: give them a visible step.
	if (!held.size && tapped.size) dt = TAP_SECONDS
	tapped.clear()
	let dx = 0
	let dy = 0
	for (const key of keys) {
		dx += DIRECTIONS[key][0]
		dy += DIRECTIONS[key][1]
	}
	if ((!keys.size && !jump) || !me.value || lifting) {
		frame = null
		moving.value = false
		if (sendTimer) sendMove()
		return
	}
	const length = Math.hypot(dx, dy)
	if (length) lastDir = [dx / length, dy / length]
	if (jump) {
		moving.value = true
		jumpStep(dt)
		scheduleSave()
		queueMove()
		checkEncounters()
		leaveMeetingIfOutside()
	}
	if (length && !jump) {
		// Diagonal moves are not faster than straight ones.
		const step = ((shift ? SHIFT_SPEED : SPEED) * dt) / length
		const maxX = me.value.cols - 1
		const maxY = me.value.rows - 1
		moving.value = true
		// No edge (PM, 2026-11-22): walking off one side brings me back on the opposite side.
		const rawX = me.value.x + dx * step
		const rawY = me.value.y + dy * step
		const x = rawX < 0 ? maxX : rawX > maxX ? 0 : rawX
		const y = rawY < 0 ? maxY : rawY > maxY ? 0 : rawY
		const wrapped = x !== rawX || y !== rawY
		// Each axis on its own, so a chip slides along another one instead of sticking to it.
		if (!blocked(x, me.value.y)) me.value.x = x
		if (!blocked(me.value.x, y)) me.value.y = y
		// The view follows my chip near its edge (#2089); after a wrap it jumps to the other side.
		if (wrapped) camera().place(me.value.x, me.value.y)
		else camera().followChip(me.value.x, me.value.y)
		scheduleSave()
		queueMove()
		checkEncounters()
		leaveMeetingIfOutside()
	}
	frame = requestAnimationFrame(tick)
}

function scheduleSave() {
	clearTimeout(saveTimer)
	saveTimer = setTimeout(save, SAVE_AFTER_MS)
}

async function save() {
	saveTimer = null
	if (!me.value) return
	const x = round(me.value.x)
	const y = round(me.value.y)
	if (saved && saved.x === x && saved.y === y) return
	try {
		await call(`${API}.save_my_position`, { x, y })
		saved = { x, y }
	} catch {
		// The next move tries again; the chip stays where the user put it meanwhile.
	}
}

let resizeObserver = null
let heartbeatTimer = null
function measure() {
	const el = stage.value
	if (!el) return
	view.width = el.clientWidth
	view.height = el.clientHeight
	// Where the stage starts in the window: the meeting view lies at fixed window px (#2091).
	const box = el.getBoundingClientRect()
	view.left = box.left
	view.top = box.top
}

onMounted(async () => {
	measure()
	resizeObserver = new ResizeObserver(measure)
	if (stage.value) resizeObserver.observe(stage.value)
	window.addEventListener("keydown", onKeydown)
	window.addEventListener("keyup", onKeyup)
	window.addEventListener("blur", releaseAll)
	window.addEventListener("pagehide", leaveOnPagehide)
	try {
		const data = await call(`${API}.get_space`)
		me.value = data.me
		// Came in (first visit of the day, or back after a while): beamed in at the start space.
		if (data.beam_in) playBeam(data.me.user)
		// The view starts on my chip (#2089).
		nextTick(() => mainCam.place(me.value.x, me.value.y))
		saved = { x: me.value.x, y: me.value.y }
		presenceTtlMs = (data.presence_ttl || 45) * 1000
		background.value = data.background || ""
		backgroundLayout.value = data.background_layout || { ...FITTED }
		backgroundRatio.value = data.background_ratio || 0
		setAreas(data.areas)
		canEditMap.value = Boolean(data.can_edit_map)
		autoCockpit.value = data.auto_cockpit !== false
		for (const notice of data.notices || []) upsertNotice(notice)
		for (const chip of data.others || []) upsertOther(chip)
	} catch (e) {
		error.value = __("Ophice could not be loaded.")
		return
	}
	checkEncounters()
	for (const [event, handler] of SOCKET_EVENTS) socket?.on?.(event, handler)
	heartbeat()
	heartbeatTimer = setInterval(heartbeat, HEARTBEAT_MS)
	loadPeople()
	peopleTimer = setInterval(loadPeople, PEOPLE_REFRESH_MS)
	loadBatchNotices()
	loadCockpits()
	startPhriend()
})

// --- Phriend on the map (#2053, PM 2026-11-22): not the floating ball of the cockpits, but standing
// on the place a map editor gave it (a space of the kind Phriend), a little bigger than a person.
// It is the real Phriend (report a problem, the reports here, its menu); Ophice only pins it there.
// Hidden while editing spaces (it would cover its own place), while a cockpit is open (the
// cockpit has its own Phriend) and when its place is off screen.

let phriend = null
let phriendTimer = null
// Phriend's width next to a person's chip (one tile): "slightly bigger".
const PHRIEND_TILES = 1.25

function startPhriend() {
	phriend = mountPhriend(router, () => __("Ophice"), socket, { pinned: true })
	if (!phriend?.ball) return
	pinPhriend()
	phriendTimer = setInterval(pinPhriend, 200)
}

function pinPhriend() {
	const ball = phriend?.ball
	if (!ball) return
	const anchor = document.querySelector("[data-phriend-anchor]")
	if (!anchor || props.cockpitOpen || editingAreas.value) return ball.pin(null)
	const spot = anchor.getBoundingClientRect()
	const box = stage.value?.getBoundingClientRect()
	const onScreen =
		spot.width > 0 && box && spot.right > box.left && spot.left < box.right && spot.bottom > box.top && spot.top < box.bottom
	if (!onScreen) return ball.pin(null)
	const size = Math.max(28, spot.width * PHRIEND_TILES)
	const height = (size * 76) / 64
	// The head on the middle of the place, the legs below it, like a chip.
	ball.pin({ left: spot.left + spot.width / 2 - size / 2, top: spot.top + spot.height / 2 - height * 0.42, size })
}

onBeforeUnmount(() => {
	clearInterval(phriendTimer)
	phriend?.ball?.pin(null)
	clearInterval(clockTimer)
	clearInterval(peopleTimer)
	clearTimeout(peopleSoon)
	window.removeEventListener("resize", onViewportResize)
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("keyup", onKeyup)
	window.removeEventListener("blur", releaseAll)
	window.removeEventListener("pagehide", leaveOnPagehide)
	for (const [event, handler] of SOCKET_EVENTS) socket?.off?.(event, handler)
	clearInterval(heartbeatTimer)
	clearTimeout(batchNoticeTimer)
	clearInterval(nowTimer)
	clearTimeout(sendTimer)
	for (const timer of movingTimers.values()) clearTimeout(timer)
	if (me.value) call(`${API}.leave`).catch(() => {})
	if (frame) cancelAnimationFrame(frame)
	resizeObserver?.disconnect()
	if (saveTimer) {
		clearTimeout(saveTimer)
		save()
	}
})
</script>

<style scoped>
/* Grid lines from the theme's outline token, so they follow light and dark mode. Only while
   areas are edited (#2067), in half tiles: the step areas snap to. */
.ophice-grid {
	--grid-cell: calc(var(--tile) / 2);
	--grid-lines: linear-gradient(to right, var(--outline-gray-2) 1px, transparent 1px),
		linear-gradient(to bottom, var(--outline-gray-2) 1px, transparent 1px);
}
.ophice-grid--lines {
	background-image: var(--grid-lines);
	background-size: var(--grid-cell) var(--grid-cell);
}
/* The camera (#2089): the canvas moves by transform only; after a drag or scroll past the edge it
   springs back with a small overshoot (the bounce). */
.ophice-viewport {
	touch-action: none;
}
.ophice-canvas {
	will-change: transform;
}
.ophice-canvas--dragging {
	cursor: grabbing;
}
.ophice-canvas--spring {
	transition: transform 380ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
@media (prefers-reduced-motion: reduce) {
	.ophice-canvas--spring {
		transition-duration: 1ms;
	}
}
/* Space chat notices (#2091): a small icon at the space; it pulses until opened once. */
.ophice-notice-icon {
	box-shadow: 0 0 0 2px #fff, 0 2px 6px rgba(0, 0, 0, 0.35);
}
.ophice-notice-icon--new {
	animation: ophice-notice-pulse 1.6s ease-out 3;
}
@keyframes ophice-notice-pulse {
	0% { box-shadow: 0 0 0 2px #fff, 0 0 0 2px rgba(239, 68, 68, 0.6); }
	70% { box-shadow: 0 0 0 2px #fff, 0 0 0 12px rgba(239, 68, 68, 0); }
	100% { box-shadow: 0 0 0 2px #fff, 0 0 0 2px rgba(239, 68, 68, 0); }
}
@media (prefers-reduced-motion: reduce) {
	.ophice-notice-icon--new {
		animation: none;
	}
}
/* "Double-click to switch" on small maps (#2091): a faint watermark. */
.ophice-switch-hint {
	font-size: 11px;
	font-weight: 600;
	letter-spacing: 0.03em;
	color: rgba(255, 255, 255, 0.85);
	text-shadow: 0 1px 3px rgba(0, 0, 0, 0.7);
	opacity: 0.75;
}
.ophice-zoom__button {
	display: flex;
	align-items: center;
	justify-content: center;
	min-width: 1.5rem;
	height: 1.5rem;
	border-radius: 0.375rem;
	color: var(--ink-gray-7);
}
.ophice-zoom__button:hover {
	background: var(--surface-gray-2);
	color: var(--ink-gray-9);
}
.ophice-chip {
	top: 0;
	left: 0;
	will-change: transform;
}
/* Beam-in (#2072): a column of light comes down onto the spot, the chip drops in and the light
   fades. Compositor-only (opacity and transform). */
.ophice-beam {
	position: absolute;
	bottom: 30%;
	left: 50%;
	width: 70%;
	height: 900%;
	pointer-events: none;
	border-radius: 999px 999px 40% 40%;
	background: linear-gradient(to top, rgba(255, 255, 255, 0.95), rgba(186, 230, 253, 0.7) 35%, rgba(186, 230, 253, 0));
	box-shadow: 0 0 24px 8px rgba(186, 230, 253, 0.55);
	transform-origin: bottom center;
	animation: ophice-beam 1600ms ease-out forwards;
}
@keyframes ophice-beam {
	0% { opacity: 0; transform: translateX(-50%) scaleX(0.2) scaleY(0.3); }
	20% { opacity: 1; transform: translateX(-50%) scaleX(1) scaleY(1); }
	65% { opacity: 0.9; transform: translateX(-50%) scaleX(0.8) scaleY(1); }
	100% { opacity: 0; transform: translateX(-50%) scaleX(0.1) scaleY(1); }
}
.ophice-beam-drop {
	animation: ophice-beam-drop 1100ms cubic-bezier(0.25, 1.4, 0.5, 1) 250ms both;
}
@keyframes ophice-beam-drop {
	0% { opacity: 0; transform: translateY(-160%) scale(calc(var(--chip-scale) * 0.4)); }
	60% { opacity: 1; transform: translateY(6%) scale(calc(var(--chip-scale) * 1.08)); }
	100% { opacity: 1; transform: translateY(0) scale(var(--chip-scale)); }
}
@media (prefers-reduced-motion: reduce) {
	.ophice-beam,
	.ophice-beam-drop {
		animation-duration: 1ms;
	}
}
/* Lifted out of a meeting space: the outer box carries the chip over the border (after the
   lift, before the set-down), the inner one rises, holds and settles with a soft squash; the
   shadow stays on the ground and shrinks while the chip is up. Compositor-only. */
.ophice-chip--lift.ophice-chip--lift {
	transition: transform 520ms cubic-bezier(0.45, 0, 0.35, 1) 200ms;
}
.ophice-lift {
	transform-origin: 50% 100%;
	animation: ophice-lift 900ms linear both;
}
@keyframes ophice-lift {
	0% { transform: translateY(0) scale(var(--chip-scale)); animation-timing-function: ease-out; }
	22% { transform: translateY(-45%) scale(calc(var(--chip-scale) * 1.12)); }
	52% { transform: translateY(-60%) scale(calc(var(--chip-scale) * 1.12)); }
	80% { transform: translateY(-8%) scale(calc(var(--chip-scale) * 1.04)); animation-timing-function: ease-in; }
	90% { transform: translateY(0) scale(calc(var(--chip-scale) * 1.06), calc(var(--chip-scale) * 0.9)); animation-timing-function: ease-out; }
	100% { transform: translateY(0) scale(var(--chip-scale)); }
}
.ophice-lift-shadow {
	position: absolute;
	bottom: 4%;
	left: 50%;
	width: 60%;
	height: 14%;
	pointer-events: none;
	border-radius: 50%;
	background: rgba(0, 0, 0, 0.28);
	animation: ophice-lift-shadow 900ms ease-in-out both;
}
@keyframes ophice-lift-shadow {
	0% { opacity: 0.8; transform: translateX(-50%) scale(1); }
	22%, 80% { opacity: 0.35; transform: translateX(-50%) scale(0.55); }
	90% { opacity: 0.9; transform: translateX(-50%) scale(1.1); }
	100% { opacity: 0; transform: translateX(-50%) scale(1); }
}
@media (prefers-reduced-motion: reduce) {
	.ophice-chip--lift.ophice-chip--lift {
		transition: none;
	}
	.ophice-lift,
	.ophice-lift-shadow {
		animation-duration: 1ms;
	}
}
/* Perimeters: a circle per chip, stronger for my own, green when touching another. A light edge
   with a thin dark outline keeps it visible on any background image, light or dark. */
.ophice-perimeter {
	top: 0;
	left: 0;
	border: 2px dashed rgba(255, 255, 255, 0.85);
	box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), inset 0 0 0 1px rgba(0, 0, 0, 0.35);
	background: rgba(255, 255, 255, 0.14);
	transition: background-color 150ms, border-color 150ms;
	will-change: transform;
}
.ophice-perimeter--me {
	border-color: rgba(96, 165, 250, 0.95);
	background: rgba(59, 130, 246, 0.18);
}
.ophice-perimeter--contact {
	border-style: solid;
	border-color: rgba(74, 222, 128, 0.95);
	background: rgba(34, 197, 94, 0.24);
}
/* Other chips arrive about 8 times a second: glide between the updates. */
.ophice-chip--remote {
	transition: transform 130ms linear;
}
@media (prefers-reduced-motion: reduce) {
	.ophice-chip--remote {
		transition: none;
	}
}
</style>
