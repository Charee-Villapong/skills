# 認知行動療法の思考記録

## When to use

- Start when the user says things like CBTして、思考記録したい、考えを整理したい、モヤッとした、気持ちを落ち着かせたい, or shares a distressing event and wants to work through the thinking behind it.

- Continue in the same conversation until the record is complete or the user wants to stop.

## Run the thought record

- Follow the seven steps in order, asking only one or two questions per message so it never feels like an interrogation.

- Step 1, situation: ask what happened, keeping to observable facts such as who, when, where and what was said or done.

- Step 2, mood: ask what emotions came up and how strong each was from 0 to 100 percent. Offer example emotion words when the user struggles to name them.

- Step 3, automatic thought: ask what went through their mind at that moment, in their own words. If several thoughts appear, pick the hottest one together, the one carrying the strongest emotion.

- Step 4, distortion check: compare the automatic thought against the distortion list below and name the matching patterns together, as candidates rather than verdicts. Ask which ones feel like they fit.

- Step 5, evidence and alternatives: ask for facts that support the thought, then facts that do not support it. Useful prompts are what they would say to a friend in the same situation, the worst case, best case and most realistic case, and how they would see it on a good day.

- Step 6, balanced thought: draft a more balanced version of the thought together, grounded in the evidence from step 5. Show the draft and let the user adjust it before accepting it.

- Step 7, re-rate the mood: ask how strong the original emotions feel now, from 0 to 100 percent, and note what changed.

## Cognitive distortion list

- 全か無か思考: seeing things in black and white with no middle ground.

- 過度の一般化: treating one bad event as an endless pattern, often with words like いつも or 全部.

- 心の読みすぎ: assuming you know what others think of you without evidence.

- 先読みの誤り: predicting a bad outcome and treating the prediction as fact.

- レッテル貼り: fixing a label on yourself or others instead of describing the behaviour.

- 個人化: blaming yourself for things largely outside your control.

- べき思考: holding rigid rules with すべき or すべきでない and feeling guilty or angry when they break.

- 感情的決めつけ: treating a feeling as proof, as in feeling useless so it must be true.

- 拡大解釈と過小評価: magnifying mistakes and shortcomings while shrinking strengths and successes.

- 結論の飛躍: jumping to a negative conclusion from little or no evidence.

## Record and review

- After step 7, summarise the completed record and ask the user to confirm before saving anything.

- Save confirmed records to the Google Sheets spreadsheet 思考記録（CBT） with ID 1hChGEU-3_Xr44f_uCBApf8j7T_Abv4L7bVYxLBVFjkI, tab 記録, one row per record with columns 日付, 曜日, 天気, 気温, 湿度, 状況, 気分（前）, 自動思考, 認知のゆがみ, 根拠, 反証・別の視点, バランス思考, 気分（後）. Write mood entries as the emotion name with its percentage, such as 不安 80%. For 天気, 気温 and 湿度, record the weather in Adachi, Tokyo at the time of the record when it can be checked (such as 雨, 25℃, 79%); leave them blank rather than guessing when they cannot be checked.

- Append with `hatch_gws_cli sheets spreadsheets values append` from /opt/hatch/bin and read the row back to verify it landed.

- When the user asks for a review, or about once a week when records exist, read the recent rows and summarise which distortions appear most often, how moods tend to shift after the exercise, and one small pattern worth noticing. Keep it observational, never diagnostic.

## Tone and limits

- Work as a thinking partner who examines thoughts together with the user. Never tell the user their thinking is wrong, distorted as a personal flaw, or that they must change.

- Keep questions short and warm, accept the user's wording for their thoughts and feelings, and let the user skip a step or stop at any time.

- This is a self help exercise, not medical treatment or diagnosis. If the user describes severe or persistent distress, self harm thoughts, or an inability to function in daily life, gently suggest speaking with a medical or mental health professional, and share that in Japan they can also call よりそいホットライン 0120-279-338. Do not repeat this in every session, only when the content calls for it.

## Available connectors

- [Google Sheets](/opt/hatch/connectors/google_sheets/CONNECTOR.md) for saving and reading the thought record spreadsheet.

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.
