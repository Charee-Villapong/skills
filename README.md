# skills

Muse（AIエージェント）への作業依頼を再現できるよう、手順書としてまとめたカスタムスキル集です。各フォルダに SKILL.md が入っていて、Claude が作業の前に読みます。

変更は Claude の VM 側からこのリポジトリへプッシュされます。

## 仕事・文章

- **cbt_thought_record** — 認知行動療法の思考記録。対話で進めてスプレッドシートに蓄積する
- **job_hunting_workflow** — 転職活動のスカウト対応ワークフロー
- **natural-japanese / natural-japanese-writing / stop-ai-slop-jp** — メールや下書きの体裁チェック（AIっぽい表現やマークダウン混入を除く）
- **spreadsheet_cutoff_prevention** — Google Sheets で文字が見切れないよう列幅・行高を決めるルール
- **spreadsheet_edit_verification** — スプレッドシート編集後の数式・グラフの検証
- **browser_login_fallback** — ブラウザのログインで詰まった時の代替手順
- **bulk_cleanup_count_reconciliation** — メールやファイルの一括整理の件数照合

## Instagram

- **ig-plan / ig-profile / ig-caption / ig-reel / ig-carousel / ig-story** — 投稿の企画・作成
- **ig-dm / ig-comment / ig-reply** — DM・コメントへの対応
- **ig-audit / ig-human / ig-viral / ig-repurpose** — 分析・改善・再利用

なお、占いPDF生成のスキル（fortune-pdf-design）は fortune リポジトリ側にあります。
