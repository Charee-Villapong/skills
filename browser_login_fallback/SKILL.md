# Browser login fallback

## Stop repeating a failed login route

- Stop after one failed attempt with the same login route.

- Name the failure plainly, such as the login card did not arrive or a bot check blocked entry.

- Try a different route only when the site offers one, such as a different sign in method or a code sent by text message.

- Stop trying new routes after the second distinct route fails and move to the fallback in the next section.

## Offer the user device fallback

- Ask the user to finish the setting on their own phone or computer when the assistant browser route fails.

- Give the exact setting to change and the exact path to it when you know the path.

- Do not claim the setting changed until the user confirms the change or you can verify the setting yourself.

- Reload the settings page and check the setting state when you have access after a change.

## Keep the requested task separate from cleanup

- Keep a requested unsubscribe or setting change separate from routine mail cleanup.

- Treat routine cleanup as backup only and say that it is backup, not a substitute for the requested change.

- Leave the requested task open until the setting change is confirmed or the user decides to stop it.

## Available connectors

- [1Password](/opt/hatch/connectors/onepassword/CONNECTOR.md) for choosing a saved login in the browser.

- [Gmail](/opt/hatch/connectors/gmail/CONNECTOR.md) for finding the sender message that led to the setting task.

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Use an unsubscribe link in the message when the sender provides one, instead of signing in first.

- Ask the user to state the setting name and its new state in their own words before you close the task.
