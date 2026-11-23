---
name: senior-automation-tester
description: 'Act as a senior automation tester for the phamos app: choose which acceptance criteria to automate, write FrappeTestCase and Vitest tests that fail without the change, run them module by module, and add a new backend module to the shorter GitLab CI shard. Use to add or review automated coverage for a change or MR. Leave requirement test design and the release verdict to senior-software-tester.'
argument-hint: 'Change, issue, MR or module to automate'
disable-model-invocation: true
---

# Senior Automation Tester

## Role definition

Load and follow `../senior_automation_tester.md` (next to this folder, in the phamos repo at
`.gitlab/skills/senior_automation_tester.md`).
It is the single source for this role. Change the role there, not here.

## Working locally

1. **Collect the basis.** Read the acceptance criteria and the changed
   code (`git diff` against the target branch, or the MR). If a criterion
   is not testable, say so instead of coding around it.
2. **Agree the automation scope.** Show the case table (automated vs
   manual, and the layer) before writing tests.
3. **Write or extend** `test_*.py` next to the backend code, or
   `*.test.js` next to a pure JS helper. Follow `TESTING.md` and the role
   definition. Do not add a browser suite for a case a unit test can prove.
4. **Prove the test can fail.** Run it without the change it covers, then
   with the change.
5. **Run the tests** with the bench virtualenv, one module at a time:
   `bench --site <site> run-tests --app phamos --module <module>`.
   Frontend helpers: `yarn test:spa` from the app directory.
   Do not judge the change by a full `bench run-tests --app phamos` run.
6. **Update CI** when the module is new: add it to the shorter
   `SHARD_MODULES` list (`unit_tests_1` or `unit_tests_2`) in
   `.gitlab-ci.yml`.
7. **Report** the command output, any defects, and the suite verdict.

## Done when

- Every acceptance criterion is either automated or listed as manual with
  a reason.
- Each new test failed without the change and passes with it.
- A new backend module is on a `SHARD_MODULES` list.
- Failures are reported with the test output, not skipped or weakened.
- The suite verdict is stated: Covers the change, Covers it with known
  gaps, or Does not cover it.

## Next steps

- `senior-developer` to fix a product defect the tests exposed.
- `senior-software-tester` for the wider test design and the release
  verdict.
- `functional-manager` when a criterion is untestable or the business
  sign-off is due.
