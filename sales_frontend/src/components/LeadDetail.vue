<template>
	<div class="flex h-full min-h-0 w-full">
		<div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
		<template v-else-if="lead">
			<!-- Master data: company/contact identity + firmographics. Rarely changes once set, but editable/fillable-in here. -->
			<section class="w-72 flex-none space-y-4 overflow-y-auto border-r border-outline-gray-2 bg-surface-white p-4">
				<FormControl v-model="companyName" label="Company" type="text" size="sm" />

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Website</label>
					<div class="flex items-center gap-1.5">
						<FormControl v-model="website" type="text" size="sm" placeholder="https://…" class="min-w-0 flex-1" />
						<button
							type="button"
							class="flex-shrink-0 rounded-md border border-outline-gray-2 p-1.5 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-40"
							:disabled="!website || checkingWebsite"
							title="Open website"
							@click="openWebsite"
						>
							<FeatherIcon :name="checkingWebsite ? 'loader' : 'maximize-2'" class="h-4 w-4" />
						</button>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-2">
					<FormControl v-model="city" label="City" type="text" size="sm" />
					<FormControl v-model="state" label="State" type="text" size="sm" />
				</div>
				<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Country</label>
						<FrappeLink doctype="Country" v-model="country" placeholder="Country" />
					</div>
				<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Territory</label>
						<FrappeLink doctype="Territory" v-model="territory" placeholder="Territory" />
					</div>
				<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Source</label>
						<FrappeLink doctype="Lead Source" v-model="source" placeholder="Source" />
					</div>
				<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Industry</label>
						<FrappeLink doctype="Industry Type" v-model="industry" placeholder="Industry" />
					</div>
				<FormControl v-model="noOfEmployees" label="No. of Employees" type="select" size="sm" :options="noOfEmployeesOptions" />
				<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Market Segment</label>
						<FrappeLink doctype="Market Segment" v-model="marketSegment" placeholder="Market Segment" />
					</div>
				<FormControl v-model="annualRevenue" label="Annual Revenue" type="number" size="sm" />
				<FormControl v-model="requestType" label="Request Type" type="select" size="sm" :options="requestTypeOptions" />
			</section>

			<!-- Communication / Notes / Activities feed — independent show/hide toggles, not exclusive tabs, so any combination (including all three) can be visible at once. -->
			<section class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface-gray-1">
				<div class="flex flex-shrink-0 flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-outline-gray-2 bg-surface-white px-4 py-3">
					<span class="text-base font-semibold text-ink-gray-9">{{ lead.lead_name || lead.name }}</span>
					<a
						v-for="number in phoneNumbers"
						:key="number"
						:href="`tel:${number}`"
						class="flex items-center gap-1.5 text-sm text-ink-gray-7 hover:text-ink-gray-9"
						@click="showNoteDialog = true"
					>
						<FeatherIcon name="phone" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5" />
						<span>{{ number }}</span>
					</a>
					<button
						v-if="lead.email_id"
						type="button"
						class="flex items-center gap-1.5 text-sm text-ink-gray-7 hover:text-ink-gray-9"
						title="Write an email"
						@click="openCompose('new')"
					>
						<FeatherIcon name="mail" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5" />
						<span class="truncate">{{ lead.email_id }}</span>
					</button>

					<!-- Everyone else on file at this company. The details to the left are
					     a copy of one person's; these chips are the rest of them. -->
					<div v-if="contacts.length" class="flex flex-wrap items-center gap-1.5">
						<button
							v-for="contact in contacts"
							:key="contact.name"
							type="button"
							class="flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
							:class="
								contact.is_primary
									? 'border-transparent bg-surface-gray-3 font-medium text-ink-gray-9'
									: 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9'
							"
							:title="contact.email_id || contact.full_name"
							@click="openContact(contact)"
						>
							<FeatherIcon
								v-if="contact.is_primary"
								name="star"
								class="h-3 w-3 flex-none text-ink-amber-3"
							/>
							<span class="max-w-[10rem] truncate">{{ contact.full_name }}</span>
						</button>
					</div>
				</div>
				<!-- Capped as a band rather than per field: each field shows as much as it
				     has, and it's the band as a whole that yields height to the feed. -->
				<div
					class="grid max-h-[33%] flex-shrink-0 grid-cols-2 gap-4 overflow-y-auto border-b border-outline-gray-2 bg-surface-white px-4 py-2.5"
				>
					<div>
						<label class="mb-1.5 flex items-center gap-1.5 text-xs text-ink-gray-5">
							<span>Status Comment</span>
							<!-- Conditionally mandatory on the doctype itself (mandatory_depends_on
							     eval:doc.status=='Do Not Contact'), so flag it rather than let the
							     save fail with a bare validation error. -->
							<span v-if="status === 'Do Not Contact'" class="text-ink-red-4">required</span>
							<span v-if="statusCommentStamp" class="ml-auto truncate text-ink-gray-5">
								{{ statusCommentStamp }}
							</span>
						</label>
						<!-- Grows with its content instead of hiding the rest behind a
						     two-line scroll — a status comment is the one thing on this
						     record people write paragraphs in. -->
						<textarea
							ref="statusCommentEl"
							v-model="statusComment"
							rows="2"
							placeholder="Reason and comments for this lead's status"
							class="form-textarea block max-h-40 w-full resize-none overflow-y-auto rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8"
							@input="autoGrowStatusComment"
						/>
					</div>

					<div ref="nextStepsRoot" class="min-w-0">
						<label class="mb-1.5 flex items-center gap-1.5 text-xs text-ink-gray-5">
							<span>Next Steps</span>
							<span
								v-if="nextSteps.length"
								class="rounded bg-surface-gray-3 px-1.5 text-xs text-ink-gray-7"
							>
								{{ nextSteps.length }}
							</span>
							<span v-if="overdueStepCount" class="ml-auto text-ink-red-4">
								{{ overdueStepCount }} overdue
							</span>
						</label>
						<!--
							Keyboard-first, mirroring ChecklistEditor: Enter opens a new row
							*below* the current one, Up/Down walk the rows, Backspace on an
							empty row removes it. Blank rows are dropped server-side on save.
						-->
						<!-- Rows read as text and become inputs on focus: quieter to scan,
						     roughly half the height, and the keyboard model is untouched. -->
						<div v-if="nextSteps.length" class="mb-1.5 space-y-0.5">
							<div
								v-for="(step, index) in visibleSteps"
								:key="step.key"
								class="group flex items-center gap-1.5 rounded border border-transparent px-0.5 focus-within:border-outline-gray-2 focus-within:bg-surface-gray-1 hover:border-outline-gray-2"
								:class="isStepOverdue(step) ? 'border-outline-red-2' : ''"
							>
								<input
									v-model="step.next_step"
									type="text"
									placeholder="Next step"
									:title="step.next_step"
									:data-step-index="index"
									data-step-field="next_step"
									class="h-6 min-w-0 flex-1 truncate border-none bg-transparent px-1 text-sm text-ink-gray-8 focus:ring-0"
									@change="scheduleNextStepsSave"
									@keydown.enter.prevent="insertStepBelow(index)"
									@keydown.down.prevent="moveStepFocus(index, 1, 'next_step')"
									@keydown.up.prevent="moveStepFocus(index, -1, 'next_step')"
									@keydown.backspace="onStepBackspace(index, $event)"
								/>
								<span
									:data-step-index="index"
									data-step-field="date"
									class="w-28 flex-none"
									:class="isStepOverdue(step) ? 'text-ink-red-4' : ''"
									@keydown.down.prevent="moveStepFocus(index, 1, 'date')"
									@keydown.up.prevent="moveStepFocus(index, -1, 'date')"
								>
									<DatePicker
										:model-value="step.date || ''"
										placeholder="Date"
										input-class="h-6 border-none bg-transparent text-xs focus:ring-0"
										@update:model-value="(value) => onStepDateChange(step, value)"
									/>
								</span>
								<button
									type="button"
									class="flex-none rounded p-0.5 text-ink-gray-5 opacity-0 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100"
									title="Remove"
									@click="removeNextStep(index)"
								>
									<FeatherIcon name="x" class="h-3.5 w-3.5" />
								</button>
							</div>
						</div>
						<div class="flex items-center gap-3">
							<!-- An explicit count beats a scrollbar nobody sees. -->
							<button
								v-if="nextSteps.length > COLLAPSED_STEPS"
								type="button"
								class="rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
								@click="showAllSteps = !showAllSteps"
							>
								{{ showAllSteps ? "Show fewer" : `Show all ${nextSteps.length}` }}
							</button>
							<button
								type="button"
								class="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
								@click="addNextStep"
							>
								<FeatherIcon name="plus" class="h-3.5 w-3.5" />
								<span>Add next step</span>
							</button>
						</div>
					</div>
				</div>
				<div class="flex flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 bg-surface-white px-4 py-2.5">
					<!-- Icon + colour per type, matching the entries below, so the row
					     doubles as the stream's legend. -->
					<button
						v-for="filter in feedFilters"
						:key="filter.key"
						type="button"
						class="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium"
						:class="activeFilters.has(filter.key) ? filter.on : filter.off"
						:aria-pressed="activeFilters.has(filter.key)"
						@click="toggleFilter(filter.key)"
					>
						<FeatherIcon :name="filter.icon" class="h-3.5 w-3.5 flex-none" />
						<span>{{ filter.label }}</span>
					</button>
					<span class="ml-auto flex items-center gap-2">
						<Button variant="subtle" @click="openCompose('new')">New Email</Button>
						<Button variant="subtle" @click="showNoteDialog = true">Add note</Button>
						<Button variant="subtle" @click="showDemoDialog = true">Create Demo</Button>
					</span>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto p-4">
					<div v-if="activityLoading" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
						Loading…
					</div>
					<div v-else-if="!activeFilters.size" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
						Select Communication, Notes, or Activities to view.
					</div>
					<div v-else-if="!timeline.length" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
						Nothing recorded yet.
					</div>
					<!-- One chronological stream: the toggles above filter which entry types appear in it. -->
					<div v-else class="space-y-2">
						<template v-for="entry in timeline" :key="entry.key">
							<!--
								Follows the Desk timeline's split: emails, notes and demos are
								cards with an icon; version/system entries are plain muted lines,
								so "what happened to the record" never competes with "what was
								said to the customer".
							-->
							<!-- Columnar so a run of changes scans down the page rather
							     than as sentences of differing length. -->
							<div
								v-if="entry.type === 'activities'"
								class="grid grid-cols-[0.9rem_minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,0.9fr)_auto] items-baseline gap-x-3 px-1 py-1 text-xs text-ink-gray-6"
							>
								<FeatherIcon name="git-commit" class="h-3.5 w-3.5 flex-none translate-y-0.5 text-ink-gray-4" />
								<span class="truncate font-medium text-ink-gray-7">{{ activityLabel(entry) }}</span>
								<span class="truncate">{{ activityDetail(entry) }}</span>
								<span class="truncate text-ink-gray-5">{{ entry.author }}</span>
								<span class="whitespace-nowrap tabular-nums text-ink-gray-5">
									{{ formatDatetime(entry.date) }}
								</span>
							</div>

							<div
								v-else
								class="rounded-md border border-l-2 border-outline-gray-2 bg-surface-white px-3 py-2.5"
								:class="entryType(entry).accent"
							>
								<div class="mb-1.5 flex items-center gap-2 text-xs text-ink-gray-5">
									<FeatherIcon
										:name="entryIcon(entry)"
										class="h-3.5 w-3.5 flex-none"
										:class="entryType(entry).iconColor"
									/>
									<Badge :label="entry.badge" :theme="entry.badgeTheme" size="sm" variant="subtle" />
									<span v-if="entry.author" class="min-w-0 truncate font-medium text-ink-gray-7">
										{{ entry.author }}
									</span>
									<span class="whitespace-nowrap">{{ formatDatetime(entry.date) }}</span>
									<button
										v-if="entry.threadSize > 1"
										type="button"
										class="flex flex-none items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900 dark:text-blue-300"
										:aria-expanded="openThreads.has(entry.threadKey)"
										@click="toggleThread(entry.threadKey)"
									>
										<FeatherIcon
											:name="openThreads.has(entry.threadKey) ? 'chevron-down' : 'chevron-right'"
											class="h-3 w-3"
										/>
										<span>{{ entry.threadSize }} messages</span>
									</button>
									<button
										v-if="entry.type === 'notes'"
										type="button"
										title="Edit note"
										class="ml-auto flex-none rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
										@click="openNoteEditor(entry)"
									>
										<FeatherIcon name="edit-2" class="h-3.5 w-3.5" />
									</button>
									<span v-if="entry.type === 'communications'" class="ml-auto flex flex-none items-center gap-1">
										<button
											type="button"
											title="Reply"
											class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
											@click="openCompose('reply', entry.communication)"
										>
											<FeatherIcon name="corner-up-left" class="h-3.5 w-3.5" />
										</button>
										<button
											type="button"
											title="Forward"
											class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
											@click="openCompose('forward', entry.communication)"
										>
											<FeatherIcon name="corner-up-right" class="h-3.5 w-3.5" />
										</button>
									</span>
								</div>

								<template v-if="entry.type === 'communications'">
									<div class="text-sm font-medium text-ink-gray-9">{{ entry.subject || "(no subject)" }}</div>

									<!-- Folded: the latest message, rendered as it was written and
									     given real room — enough to read rather than guess at. -->
									<template v-if="!openThreads.has(entry.threadKey)">
										<div v-if="entry.recipients" class="mt-0.5 truncate text-xs text-ink-gray-5">
											to {{ entry.recipients }}
										</div>
										<EmailBody class="mt-1.5" :html="entry.communication.content_html" />
										<button
											v-if="entry.threadSize > 1"
											type="button"
											class="mt-1 text-xs font-medium text-blue-700 hover:underline dark:text-blue-400"
											@click="toggleThread(entry.threadKey)"
										>
											Show {{ entry.threadSize - 1 }} earlier
											{{ entry.threadSize === 2 ? "message" : "messages" }}
										</button>
									</template>

									<!-- Unfolded: every message in the conversation, newest first. -->
									<div v-else class="mt-2 space-y-2">
										<div
											v-for="message in entry.messages"
											:key="message.name"
											class="rounded border border-outline-gray-2 px-2.5 py-2"
										>
											<div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-ink-gray-5">
												<Badge
													:label="message.sent_or_received === 'Sent' ? 'Sent' : 'Received'"
													:theme="message.sent_or_received === 'Sent' ? 'blue' : 'green'"
													size="sm"
													variant="subtle"
												/>
												<span class="min-w-0 truncate font-medium text-ink-gray-7">{{ message.sender }}</span>
												<span class="whitespace-nowrap">{{ formatDatetime(message.communication_date) }}</span>
												<span class="ml-auto flex flex-none items-center gap-1">
													<button
														type="button"
														title="Reply"
														class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
														@click="openCompose('reply', message)"
													>
														<FeatherIcon name="corner-up-left" class="h-3.5 w-3.5" />
													</button>
													<button
														type="button"
														title="Forward"
														class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
														@click="openCompose('forward', message)"
													>
														<FeatherIcon name="corner-up-right" class="h-3.5 w-3.5" />
													</button>
												</span>
											</div>
											<div v-if="message.recipients" class="mb-1 truncate text-xs text-ink-gray-5">
												to {{ message.recipients }}
											</div>
											<EmailBody :html="message.content_html" max-height-class="max-h-[22vh]" />
										</div>
									</div>
								</template>

								<template v-else-if="entry.type === 'demos'">
									<a
										:href="entry.url"
										class="text-sm font-medium text-ink-gray-9 underline-offset-2 hover:underline"
									>
										{{ entry.subject }}
									</a>
									<div v-if="entry.body" class="mt-0.5 text-xs text-ink-gray-6">{{ entry.body }}</div>
								</template>

								<div v-else class="whitespace-pre-wrap text-sm text-ink-gray-8">{{ entry.body }}</div>
							</div>
						</template>
					</div>
				</div>
			</section>

			<!-- Transactional data: changes on every follow-up, inline-editable with autosave. -->
			<section class="flex w-72 flex-none flex-col gap-5 overflow-y-auto border-l border-outline-gray-2 bg-surface-white p-4">
				<section>
					<div class="mb-2 flex items-center justify-between gap-2">
						<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Status</span>
						<button
							type="button"
							class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
							title="Back to list"
							@click="emit('close')"
						>
							<FeatherIcon name="x" class="h-4 w-4" />
						</button>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<button
							v-for="s in LEAD_STATUSES"
							:key="s"
							type="button"
							class="rounded-full disabled:opacity-50"
							:class="status === s ? 'origin-center scale-[1.15] z-[1]' : 'opacity-70 hover:opacity-100'"
							:disabled="savingStatus"
							@click="status = s"
						>
							<Badge :label="s" :theme="leadStatusTheme(s)" size="sm" :variant="status === s ? 'solid' : 'subtle'" />
						</button>
					</div>
				</section>

				<section>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Next Follow Up On</label>
					<input
						v-model="nextFollowUp"
						type="date"
						class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
					/>
				</section>

				<section>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Planned Start</label>
					<DatePicker
						:model-value="plannedStart || ''"
						placeholder="Not planned"
						input-class="h-8"
						@update:model-value="onPlannedStartChange"
					/>

					<!-- Only meaningful once there's a start month to count from. -->
					<div v-if="plannedStart" ref="predictionsRoot" class="mt-2">
						<div class="mb-1 flex items-center justify-between">
							<span class="text-xs text-ink-gray-5">Hours per month</span>
							<span v-if="totalPredictedHours" class="text-xs tabular-nums text-ink-gray-6">
								{{ totalPredictedHours }} h
							</span>
						</div>
						<div class="space-y-1">
							<div
								v-for="(row, index) in hoursPredictions"
								:key="row.month_start"
								class="flex items-center gap-1.5"
							>
								<span class="w-20 flex-none text-xs text-ink-gray-6">{{ monthLabel(row.month_start) }}</span>
								<input
									v-model="row.hours"
									type="number"
									min="0"
									step="1"
									placeholder="0"
									:data-month-index="index"
									class="form-input h-7 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
									@change="scheduleHoursSave"
									@keydown.enter.prevent="focusMonth(index + 1)"
									@keydown.down.prevent="focusMonth(index + 1)"
									@keydown.up.prevent="focusMonth(index - 1)"
								/>
							</div>
						</div>
						<button
							type="button"
							class="mt-1 flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
							@click="addMonth"
						>
							<FeatherIcon name="plus" class="h-3.5 w-3.5" />
							<span>Add month</span>
						</button>
					</div>
				</section>

				<!-- Sits with planned start and the hours predictions: what gets
				     implemented is what those hours are being predicted for. -->
				<LeadModulePicker v-model="modules" @update:model-value="scheduleModulesSave" />

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Lead Owner</label>
					<FrappeLink doctype="User" v-model="leadOwner" placeholder="Lead Owner" />
				</div>

				<FormControl
					v-model="qualificationStatus"
					label="Qualification Status"
					type="select"
					size="sm"
					:options="qualificationOptions"
				/>

				<ErrorMessage :message="saveError" />

				<a
					:href="lead.desk_url"
					class="mt-auto flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				>
					<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
					<span class="truncate">Open in Desk</span>
				</a>
			</section>
		</template>
	</div>

	<AddLeadNoteDialog v-if="lead" v-model="showNoteDialog" :lead="lead" @saved="onNoteSaved" />

	<CreateDemoDialog v-if="lead" v-model="showDemoDialog" :lead="lead" @created="onDemoCreated" />

	<ComposeEmailDialog
		v-if="lead"
		v-model="showComposeDialog"
		:lead="lead"
		:mode="composeMode"
		:source="composeSource"
		:recipient="composePrefill"
		@sent="onEmailSent"
	/>

	<LeadContactDialog
		v-if="lead && selectedContact"
		v-model="showContactDialog"
		:lead="lead"
		:contact="selectedContact"
		@changed="onPrimaryContactChanged"
		@compose="onContactCompose"
		@call="showNoteDialog = true"
	/>

	<EditLeadNoteDialog
		v-if="lead && editingNote"
		v-model="showEditNoteDialog"
		:lead="lead"
		:note="editingNote"
		@saved="onNoteEdited"
	/>

	<Dialog
		v-model="showWebsiteDialog"
		:options="{ title: lead?.company_name || lead?.lead_name || 'Website', size: '5xl' }"
	>
		<template #body-content>
			<iframe :src="websiteDialogUrl" class="h-[70vh] w-full rounded-md border border-outline-gray-2" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { call, debounce, toast, Badge, DatePicker } from "frappe-ui"
import { formatDate, formatDatetime } from "@spa/utils/datetime"
import {
	LEAD_STATUSES,
	NO_OF_EMPLOYEES_OPTIONS,
	QUALIFICATION_STATUSES,
	REQUEST_TYPE_OPTIONS,
	leadStatusTheme,
} from "@/leadListColumns.js"
import FrappeLink from "@spa/components/FrappeLink.vue"
import LeadModulePicker from "./LeadModulePicker.vue"
import AddLeadNoteDialog from "./AddLeadNoteDialog.vue"
import CreateDemoDialog from "./CreateDemoDialog.vue"
import EditLeadNoteDialog from "./EditLeadNoteDialog.vue"
import ComposeEmailDialog from "./ComposeEmailDialog.vue"
import EmailBody from "./EmailBody.vue"
import LeadContactDialog from "./LeadContactDialog.vue"

const API = "phamos.api.sales_leads"
const DEMOS_API = "phamos.api.sales_demos"

const props = defineProps({
	name: { type: String, required: true },
})

const emit = defineEmits(["close", "updated"])

const lead = ref(null)
const loading = ref(false)
const syncing = ref(false)
const savingStatus = ref(false)
const saveError = ref("")
const showNoteDialog = ref(false)
const contacts = ref([])
const selectedContact = ref(null)
const showContactDialog = ref(false)
const composePrefill = ref("")
const showWebsiteDialog = ref(false)
const showDemoDialog = ref(false)
const showEditNoteDialog = ref(false)
const editingNote = ref(null)
const showComposeDialog = ref(false)
const composeMode = ref("new")
const composeSource = ref(null)
const checkingWebsite = ref(false)

const status = ref("")
// Date-only (YYYY-MM-DD), bound straight to an <input type="date">: no
// timezone conversion, which would shift a bare date across day boundaries.
const nextFollowUp = ref("")
const qualificationStatus = ref("")
const statusComment = ref("")
const leadOwner = ref("")
// Local working copy of the Lead's Next Steps child table; saved as a whole
// (see set_lead_next_steps) rather than row by row.
const demos = ref([])
const modules = ref([])
const plannedStart = ref("")
const hoursPredictions = ref([])
const predictionsRoot = ref(null)
const DEFAULT_PREDICTION_MONTHS = 3
const nextSteps = ref([])
const nextStepsRoot = ref(null)
const statusCommentEl = ref(null)
/** Rows shown before the "Show all" expander takes over. */
const COLLAPSED_STEPS = 5
const showAllSteps = ref(false)

const visibleSteps = computed(() =>
	showAllSteps.value ? nextSteps.value : nextSteps.value.slice(0, COLLAPSED_STEPS)
)

/** Local midnight, so "today" isn't overdue. */
function isStepOverdue(step) {
	if (!step.date) return false
	const today = new Date()
	today.setHours(0, 0, 0, 0)
	return new Date(`${String(step.date).slice(0, 10)}T00:00:00`) < today
}

const overdueStepCount = computed(() => nextSteps.value.filter(isStepOverdue).length)

const statusCommentStamp = computed(() => {
	const who = lead.value?.custom_status_comment_modified_by_name
	const when = lead.value?.custom_status_comment_modified_date
	if (!who && !when) return ""
	return [who, when ? formatDate(when) : ""].filter(Boolean).join(" · ")
})

/** A comment shows all of itself, up to the field's own max height. */
function autoGrowStatusComment() {
	const el = statusCommentEl.value
	if (!el) return
	el.style.height = "auto"
	el.style.height = `${el.scrollHeight}px`
}
// Stable per-row key so re-sorting moves DOM nodes (and keeps focus with the
// row) instead of rewriting values in place.
let nextStepKey = 0

const companyName = ref("")
const website = ref("")
const city = ref("")
const state = ref("")
const country = ref("")
const territory = ref("")
const source = ref("")
const industry = ref("")
const noOfEmployees = ref("")
const marketSegment = ref("")
const annualRevenue = ref("")
const requestType = ref("")

const activityLoading = ref(false)
const notes = ref([])
const communications = ref([])
const activities = ref([])
// Independent show/hide toggles (not exclusive tabs) — any combination,
// including all three at once, can be visible together.
const activeFilters = ref(new Set(["communications", "demos"]))

/**
 * Each entry type owns an icon and a colour, used identically on the filter
 * chip and on the entries themselves, so the toggle reads as a legend for the
 * stream below it.
 */
const FEED_TYPES = {
	communications: {
		label: "Communication",
		icon: "mail",
		on: "bg-blue-600 text-white",
		off: "text-blue-700 hover:bg-blue-50 dark:text-blue-400",
		accent: "border-l-blue-500",
		iconColor: "text-blue-600",
	},
	notes: {
		label: "Notes",
		icon: "message-square",
		on: "bg-amber-600 text-white",
		off: "text-amber-700 hover:bg-amber-50 dark:text-amber-400",
		accent: "border-l-amber-500",
		iconColor: "text-amber-600",
	},
	activities: {
		label: "Activities",
		icon: "git-commit",
		on: "bg-gray-700 text-white",
		off: "text-ink-gray-6 hover:bg-surface-gray-2",
		accent: "border-l-gray-400",
		iconColor: "text-ink-gray-5",
	},
	demos: {
		label: "Demos",
		icon: "monitor",
		on: "bg-purple-600 text-white",
		off: "text-purple-700 hover:bg-purple-50 dark:text-purple-400",
		accent: "border-l-purple-500",
		iconColor: "text-purple-600",
	},
}

const feedFilters = Object.entries(FEED_TYPES).map(([key, type]) => ({ key, ...type }))

/** Threads the user has opened, by thread key. */
const openThreads = ref(new Set())

function toggleThread(key) {
	const next = new Set(openThreads.value)
	if (next.has(key)) next.delete(key)
	else next.add(key)
	openThreads.value = next
}

function toggleFilter(key) {
	const next = new Set(activeFilters.value)
	if (next.has(key)) next.delete(key)
	else next.add(key)
	activeFilters.value = next
}

/** Communications, notes and activities merged into one chronological stream. */
const timeline = computed(() => {
	const entries = []

	if (activeFilters.value.has("communications")) {
		// One entry per conversation, not per message: a thread is the unit
		// people think in, and stacking it keeps a long back-and-forth from
		// burying everything else in the stream.
		const threads = new Map()
		for (const comm of communications.value) {
			const key = comm.thread_key || comm.name
			if (!threads.has(key)) threads.set(key, [])
			threads.get(key).push(comm)
		}

		for (const [key, messages] of threads) {
			// Backend returns newest first; keep that order inside the thread.
			const latest = messages[0]
			entries.push({
				key: `thread:${key}`,
				type: "communications",
				date: latest.communication_date,
				badge: latest.sent_or_received === "Sent" ? "Sent" : "Received",
				badgeTheme: latest.sent_or_received === "Sent" ? "blue" : "green",
				author: latest.sender,
				sender: latest.sender,
				recipients: latest.recipients,
				subject: latest.subject,
				threadSize: messages.length,
				threadKey: key,
				messages,
				communication: latest,
			})
		}
	}

	if (activeFilters.value.has("notes")) {
		for (const note of notes.value) {
			entries.push({
				key: `note:${note.name}`,
				type: "notes",
				date: note.added_on,
				badge: "Note",
				badgeTheme: "orange",
				author: note.added_by_name || note.added_by,
				body: stripHtml(note.note),
				note,
			})
		}
	}

	if (activeFilters.value.has("demos")) {
		for (const demo of demos.value) {
			entries.push({
				key: `demo:${demo.name}`,
				type: "demos",
				// Unscheduled demos still belong in the stream, so fall back to
				// when the record last moved.
				date: demo.scheduled_on || demo.modified,
				badge: "Demo",
				badgeTheme: "blue",
				author: demo.owner_name || demo.owner,
				subject: demo.subject || demo.name,
				body: demo.scheduled_on ? "" : "Awaiting a date",
				url: `/app/demo/${demo.name}`,
			})
		}
	}

	if (activeFilters.value.has("activities")) {
		activities.value.forEach((activity, index) => {
			entries.push({
				key: `activity:${index}`,
				type: "activities",
				date: activity.creation,
				badge: "Activity",
				badgeTheme: "gray",
				author: activity.owner,
				activity,
				fieldChange: activity.kind === "field_change" ? activity : null,
				body: stripHtml(activity.content),
			})
		})
	}

	return entries.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
})

const qualificationOptions = computed(() => [
	{ label: "—", value: "" },
	...QUALIFICATION_STATUSES.map((q) => ({ label: q, value: q })),
])

const noOfEmployeesOptions = computed(() => [
	{ label: "—", value: "" },
	...NO_OF_EMPLOYEES_OPTIONS.map((o) => ({ label: o, value: o })),
])

const requestTypeOptions = computed(() => [
	{ label: "—", value: "" },
	...REQUEST_TYPE_OPTIONS.map((o) => ({ label: o, value: o })),
])

const phoneNumbers = computed(() => [...new Set([lead.value?.mobile_no, lead.value?.phone].filter(Boolean))])

/** Left column: what was touched. */
function activityLabel(entry) {
	return entry.activity?.label || entry.fieldChange?.label || "Update"
}

/** Middle column: what changed about it. */
function activityDetail(entry) {
	const activity = entry.activity
	if (activity?.kind === "row_added") return `Added: ${activity.summary || "—"}`
	if (activity?.kind === "row_removed") return `Removed: ${activity.summary || "—"}`
	if (entry.fieldChange) return `${entry.fieldChange.old || "—"} → ${entry.fieldChange.new || "—"}`
	return entry.body || ""
}

function entryType(entry) {
	return FEED_TYPES[entry.type] || FEED_TYPES.activities
}

function entryIcon(entry) {
	return entryType(entry).icon
}

// Resolved server-side by check_website_embeddable (normalized + redirects
// followed), set only once we know the site will actually render framed.
const websiteDialogUrl = ref("")

async function openWebsite() {
	if (!website.value || checkingWebsite.value) return
	checkingWebsite.value = true
	try {
		const result = await call(`${API}.check_website_embeddable`, { url: website.value })
		if (result.embeddable) {
			websiteDialogUrl.value = result.url
			showWebsiteDialog.value = true
			return
		}
		// Can't be framed (or didn't respond) — open a tab instead of showing a blank dialog.
		window.open(result.url, "_blank", "noopener")
		toast({
			title:
				result.reason === "blocked"
					? "This site blocks embedding, so it opened in a new tab."
					: "Could not reach this site to preview it — opened in a new tab.",
			icon: "alert-triangle",
			iconClasses: "text-ink-amber-3",
		})
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not open website",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	} finally {
		checkingWebsite.value = false
	}
}

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function syncFieldsFromLead() {
	syncing.value = true
	status.value = lead.value.status || ""
	nextFollowUp.value = lead.value.custom_next_followup || ""
	qualificationStatus.value = lead.value.qualification_status || ""
	statusComment.value = lead.value.custom_status_comment || ""
	// Size the box to a stored comment on arrival, not after the first keystroke.
	nextTick(autoGrowStatusComment)
	leadOwner.value = lead.value.lead_owner || ""
	plannedStart.value = lead.value.custom_planned_start || ""
	hoursPredictions.value = (lead.value.hours_predictions || []).map((row) => ({
		month_start: row.month_start,
		hours: row.hours ?? "",
	}))
	if (plannedStart.value && !hoursPredictions.value.length) {
		seedPredictionMonths()
	}
	modules.value = (lead.value.modules || []).map((row) => ({
		module: row.module,
		module_name: row.module_name,
	}))
	nextSteps.value = (lead.value.next_steps || []).map((step) => ({
		key: nextStepKey++,
		next_step: step.next_step || "",
		date: step.date || "",
	}))
	sortNextSteps()
	companyName.value = lead.value.company_name || ""
	website.value = lead.value.website || ""
	city.value = lead.value.city || ""
	state.value = lead.value.state || ""
	country.value = lead.value.country || ""
	territory.value = lead.value.territory || ""
	source.value = lead.value.source || ""
	industry.value = lead.value.industry || ""
	noOfEmployees.value = lead.value.no_of_employees || ""
	marketSegment.value = lead.value.market_segment || ""
	annualRevenue.value = lead.value.annual_revenue ?? ""
	requestType.value = lead.value.request_type || ""
	saveError.value = ""
	nextTick(() => {
		syncing.value = false
	})
}

async function loadLead() {
	loading.value = true
	try {
		lead.value = await call(`${API}.get_lead`, { name: props.name })
		syncFieldsFromLead()
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not load lead",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	} finally {
		loading.value = false
	}
}

async function loadDemos() {
	try {
		const data = await call(`${DEMOS_API}.get_demos`, { lead: props.name })
		demos.value = data.items || []
	} catch (e) {
		demos.value = []
	}
}

async function loadContacts() {
	try {
		const data = await call(`${API}.get_lead_contacts`, { lead: props.name })
		contacts.value = data.contacts || []
	} catch (e) {
		contacts.value = []
	}
}

function openContact(contact) {
	selectedContact.value = contact
	showContactDialog.value = true
}

function onContactCompose(email) {
	showContactDialog.value = false
	openCompose("new", null, email)
}

/** The header's details are now someone else's — reload both sides of it. */
async function onPrimaryContactChanged(updated) {
	lead.value = { ...lead.value, ...updated }
	syncFieldsFromLead()
	await loadContacts()
	emit("updated", lead.value)
	loadActivity()
}

async function loadActivity() {
	activityLoading.value = true
	try {
		const data = await call(`${API}.get_lead_activity`, { name: props.name })
		notes.value = data.notes || []
		communications.value = data.communications || []
		activities.value = data.activities || []
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not load activity",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	} finally {
		activityLoading.value = false
	}
}

async function saveFields() {
	if (syncing.value || !lead.value) return
	saveError.value = ""
	savingStatus.value = true
	try {
		const updated = await call(`${API}.update_lead`, {
			name: lead.value.name,
			status: status.value,
			custom_next_followup: nextFollowUp.value,
			qualification_status: qualificationStatus.value,
			custom_status_comment: statusComment.value,
			lead_owner: leadOwner.value,
			custom_planned_start: plannedStart.value,
			company_name: companyName.value,
			website: website.value,
			city: city.value,
			state: state.value,
			country: country.value,
			territory: territory.value,
			source: source.value,
			industry: industry.value,
			no_of_employees: noOfEmployees.value,
			market_segment: marketSegment.value,
			annual_revenue: annualRevenue.value === "" ? 0 : annualRevenue.value,
			request_type: requestType.value,
			if_modified: lead.value.modified,
		})
		if (updated.conflict) {
			toast({
				title: "Saved — but this Lead was also changed by someone else just now. Check for lost edits.",
				icon: "alert-triangle",
				iconClasses: "text-ink-amber-3",
			})
		}
		delete updated.conflict
		lead.value = updated
		syncFieldsFromLead()
		emit("updated", updated)
	} catch (e) {
		saveError.value = e?.messages?.[0] || e?.message || "Could not save lead"
		toast({ title: saveError.value, icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		savingStatus.value = false
	}
}

const scheduleSave = debounce(() => {
	saveFields()
}, 500)

async function saveNextSteps() {
	if (syncing.value || !lead.value) return
	try {
		const saved = await call(`${API}.set_lead_next_steps`, {
			lead: lead.value.name,
			rows: nextSteps.value
				.filter((step) => (step.next_step || "").trim())
				.map((step) => ({ next_step: step.next_step, date: step.date || null })),
		})
		lead.value = { ...lead.value, next_steps: saved }
		// The add/remove lands in the Lead's version history, so refresh the
		// feed to surface it under Activities without a reload.
		loadActivity()
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not save next steps",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	}
}

async function saveModules() {
	if (syncing.value || !lead.value) return
	try {
		const saved = await call(`${API}.set_lead_modules`, {
			lead: lead.value.name,
			modules: modules.value.map((row) => ({ module: row.module })),
		})
		lead.value = { ...lead.value, modules: saved }
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not save modules",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	}
}

const scheduleModulesSave = debounce(() => {
	saveModules()
}, 400)

const scheduleNextStepsSave = debounce(() => {
	saveNextSteps()
}, 500)

/** Focus a row's input by position. The text cell carries the marker itself;
 *  the date cell is a wrapper around frappe-ui's DatePicker, so look inside. */
function focusStep(index, field = "next_step") {
	nextTick(() => {
		const cell = nextStepsRoot.value?.querySelector(
			`[data-step-index="${index}"][data-step-field="${field}"]`
		)
		const input = cell?.matches?.("input") ? cell : cell?.querySelector("input")
		input?.focus()
	})
}

/** Date ascending, undated rows last. */
function sortNextSteps() {
	nextSteps.value.sort((a, b) => {
		if (!a.date && !b.date) return 0
		if (!a.date) return 1
		if (!b.date) return -1
		return String(a.date).localeCompare(String(b.date))
	})
}

function onStepDateChange(step, value) {
	step.date = value || ""
	// Re-sort once the date is committed (not while typing the text), so rows
	// don't shuffle under the cursor mid-edit. Rows are keyed, so Vue moves the
	// existing nodes and focus follows the row rather than the position.
	sortNextSteps()
	scheduleNextStepsSave()
}

/** First of the month, as YYYY-MM-01. */
function monthStart(dateStr, offset = 0) {
	const [year, month] = String(dateStr).slice(0, 10).split("-").map(Number)
	const date = new Date(year, month - 1 + offset, 1)
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`
}

function monthLabel(monthStartValue) {
	const [year, month] = String(monthStartValue).slice(0, 10).split("-").map(Number)
	return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" })
}

const totalPredictedHours = computed(() =>
	hoursPredictions.value.reduce((sum, row) => sum + (Number(row.hours) || 0), 0)
)

/** Months run from the planned start, so the first row is that month. */
function seedPredictionMonths() {
	hoursPredictions.value = Array.from({ length: DEFAULT_PREDICTION_MONTHS }, (_, i) => ({
		month_start: monthStart(plannedStart.value, i),
		hours: "",
	}))
}

function addMonth() {
	const last = hoursPredictions.value[hoursPredictions.value.length - 1]
	const next = last ? monthStart(last.month_start, 1) : monthStart(plannedStart.value)
	hoursPredictions.value.push({ month_start: next, hours: "" })
	focusMonth(hoursPredictions.value.length - 1)
}

function focusMonth(index) {
	if (index < 0 || index >= hoursPredictions.value.length) return
	nextTick(() => {
		predictionsRoot.value?.querySelector(`input[data-month-index="${index}"]`)?.focus()
	})
}

async function onPlannedStartChange(value) {
	plannedStart.value = value || ""
	// Re-anchor the months when the start moves, but don't discard numbers
	// already entered for months that still apply.
	if (plannedStart.value) {
		const existing = new Map(hoursPredictions.value.map((r) => [r.month_start, r.hours]))
		const count = Math.max(hoursPredictions.value.length, DEFAULT_PREDICTION_MONTHS)
		hoursPredictions.value = Array.from({ length: count }, (_, i) => {
			const month = monthStart(plannedStart.value, i)
			return { month_start: month, hours: existing.get(month) ?? "" }
		})
	}
	await saveFields()
	saveHoursPredictions()
}

async function saveHoursPredictions() {
	if (syncing.value || !lead.value) return
	try {
		const saved = await call(`${API}.set_lead_hours_predictions`, {
			lead: lead.value.name,
			rows: hoursPredictions.value
				.filter((row) => row.hours !== "" && row.hours !== null)
				.map((row) => ({ month_start: row.month_start, hours: Number(row.hours) || 0 })),
		})
		lead.value = { ...lead.value, hours_predictions: saved }
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not save hours predictions",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	}
}

const scheduleHoursSave = debounce(() => {
	saveHoursPredictions()
}, 500)

function addNextStep() {
	// Never create a row behind the fold.
	showAllSteps.value = true
	nextSteps.value.push({ key: nextStepKey++, next_step: "", date: "" })
	focusStep(nextSteps.value.length - 1)
}

/** Enter opens the next row directly below the current one, never above it. */
function insertStepBelow(index) {
	showAllSteps.value = true
	nextSteps.value.splice(index + 1, 0, { key: nextStepKey++, next_step: "", date: "" })
	focusStep(index + 1)
}

function moveStepFocus(index, delta, field) {
	const target = index + delta
	if (target < 0 || target >= nextSteps.value.length) return
	// Walking past the fold opens it rather than dead-ending.
	if (target >= COLLAPSED_STEPS) showAllSteps.value = true
	focusStep(target, field)
}

function onStepBackspace(index, event) {
	// Only swallow Backspace when the row is empty — otherwise it's normal editing.
	if ((nextSteps.value[index]?.next_step || "").length) return
	event.preventDefault()
	removeNextStep(index)
	if (nextSteps.value.length) focusStep(Math.max(0, index - 1))
}

function removeNextStep(index) {
	nextSteps.value.splice(index, 1)
	saveNextSteps()
}

watch(
	[
		status,
		nextFollowUp,
		qualificationStatus,
		statusComment,
		leadOwner,
		companyName,
		website,
		city,
		state,
		country,
		territory,
		source,
		industry,
		noOfEmployees,
		marketSegment,
		annualRevenue,
		requestType,
	],
	() => {
		if (syncing.value) return
		scheduleSave()
	}
)

function onDemoCreated() {
	// The demo's Event lands in the Lead's timeline, so refresh the feed.
	loadActivity()
	loadDemos()
	toast({ title: "Demo created", icon: "check-circle", iconClasses: "text-ink-green-4" })
}

function openCompose(mode, communication = null, recipient = "") {
	composeMode.value = mode
	composeSource.value = communication
	composePrefill.value = recipient
	showComposeDialog.value = true
}

function onEmailSent() {
	// The sent mail is filed against the lead, so it shows up in the feed.
	loadActivity()
	toast({ title: "Email sent", icon: "check-circle", iconClasses: "text-ink-green-4" })
}

function openNoteEditor(entry) {
	editingNote.value = entry.note
	showEditNoteDialog.value = true
}

function onNoteEdited(savedNotes) {
	notes.value = savedNotes || []
}

function onNoteSaved(updated) {
	lead.value = { ...lead.value, ...updated }
	syncFieldsFromLead()
	emit("updated", lead.value)
	loadActivity()
}

function loadAll() {
	loadLead()
	loadActivity()
	loadDemos()
	loadContacts()
}

onMounted(() => {
	loadAll()
})

watch(
	() => props.name,
	() => {
		loadAll()
	}
)
</script>

