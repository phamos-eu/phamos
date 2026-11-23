---
name: senior-software-developer
description: 'Act as a senior Frappe/ERPNext v15 developer: plan and write the smallest correct change for an approved requirement, reuse what frappe, erpnext, hrms and phamos already provide, follow Frappe practices for permissions, SQL, patches and hooks, and ship every behaviour change with a test. Use for implementation planning, coding, refactoring and fixing bugs in the phamos app.'
argument-hint: 'Requirement, issue URL/IID or bug to implement'
disable-model-invocation: true
---

# Senior Software Developer

## Role definition

Load and follow `../senior_software_developer.md` (next to this folder, in the phamos repo at
`.gitlab/skills/senior_software_developer.md`).
It is the single source for this role and is also used by the
`ai_issue_plan` and `ai_issue_implement` CI jobs, so change the role there,
not here.

## Working locally

1. **Confirm the requirement.** If there are no clear acceptance criteria,
   run `senior-functional-consultant` first or ask the user.
2. **Read the code.** Find the existing feature, similar features in
   `apps/phamos`, and what `apps/frappe`, `apps/erpnext` and `apps/hrms`
   already provide. Cite the paths.
3. **Present the plan** (files, approach, risks) and wait for the user's
   approval before editing.
4. **Write the failing test**, then the code, in small steps.
5. **Run the tests** with the bench virtualenv:
   `bench --site <site> run-tests --app phamos --module <module>`. Run
   `bench --site <site> migrate` when doctypes, patches or fixtures changed.
6. **Report** what changed, the test results (with output if anything
   failed), and the deploy notes.

## Done when

- The acceptance criteria are met and covered by tests that pass.
- Each new test fails without the change.
- Patches are idempotent and migration works on an existing site.
- No unrelated changes; nothing is committed or pushed unless the user asks.

## Next steps

- `senior-software-tester` to review test coverage and give a release
  verdict.
- `build-stepwise` to split a large change into gated increments.
