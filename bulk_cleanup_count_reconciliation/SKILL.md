# Bulk cleanup count reconciliation

## Separate the counts before you act

- Define five buckets before you touch anything and keep them apart through the whole run.

- Count searched items as only the items your search returned in the stated scope.

- Count already done items as items already trashed or archived by an earlier run in the same scope.

- Count newly done items as only the items this run moves to trash or archive.

- Count kept items as items you deliberately leave in place, including important mail and files you cannot trash because another person owns them.

- Count restored items as items you moved back after an earlier mistake, and never add them to a newly done total.

## Count only from the executed log

- Read the executed log after the run finishes and build every number from that log.

- Exclude already done items from the newly done total even when they appeared in your search.

- Recheck the scope when the searched total and the executed total differ, and resolve the gap before you report anything.

- State the search scope with each count, including the sender or folder and the date range you used.

- Treat a search result as a candidate list, never as proof that an action happened.

## Report the split and correct it plainly

- Report searched, already done, newly done, kept and restored as separate numbers in every bulk cleanup report.

- Never report the searched total as the number you actioned.

- Name the kept items by category when you keep important mail or shared files, and say why each category stayed.

- Correct a published total in the same message thread as soon as you find an error, and show the old number beside the corrected number.

- Hold the first report until the split reconciles, rather than publishing a total and correcting it later.

## Available connectors

- [Gmail](/opt/hatch/connectors/gmail/CONNECTOR.md) for searching, counting, trashing and restoring Gmail messages.

- [Google Drive](/opt/hatch/connectors/google_drive/CONNECTOR.md) for finding and trashing Drive files and checking who owns each file.

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Run a small pilot batch first when the search returns a large total, and reconcile that batch before you run the rest.

- Ask the user to confirm the kept categories before a large run, so important mail stays out of the bulk action from the start.
