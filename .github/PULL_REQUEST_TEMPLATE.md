## **Pull Request Description Template:**

Use Markdown for formatting.

**Markdown**

\`## Description

\[Clearly and concisely describe the changes introduced by this pull request. Explain the "why" behind the changes and the approach taken. Provide context where necessary.\]

**Key changes:**

* \[List the most important changes made. Be specific. Use bullet points or numbered lists.\]
* \[Example: Implemented two-factor authentication using TOTP.\]
* \[Example: Fixed a bug where dates were displayed in the wrong format in the user profile section.\]
* \[Example: Added a new setting to allow users to switch between light and dark mode.\]

**Related issue(s)/ticket(s):**

* \[Link to any related issues or tickets. Use keywords like "Fixes," "Resolves," "Closes," or "Relates to."\]
* \[The link preferably should be a link to a GitLab issue. If possible, also add a link to the Mattermost thread. The important thing is to have enough context to review the Pull Request.\]
* \[Example: GitLab Issue https://git.phamos.eu/suncycle/suncycle/-/issues/281\\\]
* \[Example: Mattermost Thread https://chat.phamos.eu/team-danny/pl/gsyxrqm3aprni86zwnzic89rra\\\]
* \[Example: Fixes #123, Closes #456\]

**Testing done:**

* \[Describe the testing performed to ensure the changes are working as expected. Be specific about the test cases and scenarios covered.\]
* \[Example: Manually tested login with two-factor authentication enabled and disabled.\]
* \[Example: Ran unit tests and integration tests for the date formatting functionality.\]
* \[Example: Tested dark mode on Chrome, Firefox, and Safari.\]

**Screenshots & GIFs (if applicable):**

* \[Include screenshots to visually demonstrate the changes, especially for UI changes.\]
* \[The screenshot should be marked with highlighters, rectangles, arrows, or any form of visual representation to focus on the area of the image that matters.\]
* \[Make sure not to include any screenshots that show real customer data, for example: addresses, names, numbers, etc.\]
* \[Include GIFs to understand the workflow and process better.\]
* \[Example: https://github.com/suncycle-eu/suncycle/pull/464\]

**Further comments/notes (optional):**

* \[Add any additional information that might be helpful for reviewers. This could include potential edge cases, limitations, or alternative approaches considered.\]
* \[Example: Considered using SMS-based authentication but decided to go with TOTP for better security.\]

**Checklist:**

* [ ] I followed this (guideline)[https://doku.phamos.eu/books/developer-onboarding/page/pull-request-creation]
* [ ] I created feature branch from develop
* [ ] The name of the feature branch follows conventions
* [ ] I created logical commit with a clear messages
* [ ] I pulled the changes from develop (again) and resolve possible conflicts
* [ ] I pushed changes to remote feature branch
* [ ] I created a Pull Request with title and description as described in the guideline
* [ ] I checked if there is any conflict after creating the PR