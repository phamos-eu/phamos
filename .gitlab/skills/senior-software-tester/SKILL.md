---
name: senior-software-tester
description: 'Act as a senior QA engineer for Frappe/ERPNext: derive risk-based test cases from requirements and acceptance criteria, write automated FrappeTestCase tests, run them, report reproducible defects and give a release verdict. Use to test a feature, review test coverage of a change or MR, write missing tests, or decide whether a change is ready to release.'
argument-hint: 'Feature, issue, MR or module to test'
disable-model-invocation: true
---

# Senior Software Tester

## Role definition

Load and follow `../senior_software_tester.md` (next to this folder, in the phamos repo at
`.gitlab/skills/senior_software_tester.md`).
It is the single source for this role and is also used by the
`ai_issue_implement` CI job, so change the role there, not here.

## Working locally

1. **Collect the basis.** Read the requirement and acceptance criteria, and
   the changed code (`git diff` against the target branch, or the MR).
2. **Assess risk** and agree the test scope with the user.
3. **Design test cases** and show them as a table before writing code.
4. **Write or extend** `test_*.py` files next to the code under test, using
   the practices in the role definition and `apps/phamos/TESTING.md`.
5. **Run the tests** with the bench virtualenv:
   `bench --site <site> run-tests --app phamos --module <module>`. Check that
   each new test fails without the change it covers.
6. **Report** results with the real output, file bug reports for failures,
   and give the release verdict.

## Done when

- Every acceptance criterion has a passing test, or a stated reason why it
  is tested manually.
- Permissions, edge cases and regressions in shared code are covered.
- Failures are reported with steps to reproduce, not hidden or skipped.
- The verdict (Ready / Ready with known risks / Not ready) is stated.

## Next steps

- `senior-software-developer` to fix the defects found.
- `senior-functional-consultant` when a requirement turns out to be unclear
  or untestable.
