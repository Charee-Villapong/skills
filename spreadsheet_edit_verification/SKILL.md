# Spreadsheet structural edit verification

## Map the sheet before you change its structure

- List every summary block, formula range and chart on the tab before you insert rows, delete rows, hide columns or move a block.

- Record each summary position and each formula range you will touch before you edit anything.

- Record which columns a chart reads before you hide a column.

- Ask the user which columns may stay visible when the visible layout is unclear, rather than hiding a wide range on your own.

## Insert and hide without breaking dependents

- Insert rows only at a position that does not overwrite an existing data row, and check the row below the insert point after the insert.

- Keep a summary block and its formula ranges intact when you insert rows above it, and restore its position and ranges when the insert moves them.

- Hide columns instead of deleting them when the data may be needed again, and keep the chart source columns visible when a chart depends on them.

- Undo a change at once when a check shows a row overwritten or a formula shifted, and restore the earlier state before you try again.

## Verify before you report

- Read the tab again after every structural change and compare each summary position and formula range with the record you made before the change.

- Check each chart on the tab after hiding columns and confirm that it still shows its data.

- Report the change only after the recheck passes, and name any item you restored during the check.

- Do not report a total or a chart as correct when the recheck is still open.

## Available connectors

- [Google Sheets](/opt/hatch/connectors/google_sheets/CONNECTOR.md) for editing a live workbook without replacing it.

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Test a small change on one row or column first when the restructure is large, and verify it before you apply the same change widely.

- Ask the user to approve a fixed summary position before you move a summary block, instead of moving it on your own.
