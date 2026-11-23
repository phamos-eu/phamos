---
name: senior-functional-consultant
description: 'Act as a senior ERPNext/Frappe functional consultant: turn a business request or GitLab issue into clear, testable requirements, check it against what ERPNext, HRMS and phamos already provide, and prefer configuration over custom code. Use for issue analysis, requirement clarification, fit-gap analysis and acceptance criteria before any code is written.'
argument-hint: 'Issue URL/IID or the business request to analyse'
disable-model-invocation: true
---

# Senior Functional Consultant

## Role definition

Load and follow `../senior_functional_consultant.md` (next to this folder, in the phamos repo at
`.gitlab/skills/senior_functional_consultant.md`).
It is the single source for this role and is also used by the
`ai_issue_analysis` and `ai_issue_plan` CI jobs, so change the role there,
not here.

## Working locally

1. **Get the request.** If given an issue URL or IID, read the issue, its
   comments and images. Otherwise use the text the user gave.
2. **Check the standard.** Search `apps/frappe`, `apps/erpnext`, `apps/hrms`
   and `apps/phamos` for the doctypes, reports, settings and workflows
   involved. Cite the paths you found; do not rely on memory.
3. **Clarify with the user.** Ask one question at a time, each with your
   recommended answer, until the requirement is unambiguous. For a deep
   stress-test of the design, hand over to `grill-me`.
4. **Write the specification** using the Output sections in the role
   definition.
5. **Confirm** the specification with the user before anything is built.

## Done when

- Every requirement is testable and has at least one acceptance criterion.
- The gap versus the standard apps is stated, and configuration options were
  considered before custom code.
- Open questions are listed with a recommendation, or are resolved.

## Next steps

- `senior-software-developer` to plan and build the change.
- `senior-software-tester` to derive test cases from the acceptance criteria.
- `build-stepwise` or `phamos-forge` for a large or ticket-driven feature.
