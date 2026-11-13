# natural-japanese-writing

AI が書いたように読める日本語を、事実を変えずに自然な日本語へ直すスキルです。

文書の種類（業務文書・読み物・説明文）を先に決め、表記・語彙・文末とリズム・構文・構成・中身の6つの層で点検します。

## ツール

### scripts/overlap_judgement.py（癖の重なり判定）

`scripts/check.py` の検出出力を入力として、「考え方」節の重なり判定を行います。同じ段落に違う種類の癖が3つ以上重なれば修正対象、★印の癖は1つで修正対象です。同じ癖の繰り返しは1種と数えます。判定に必要な入力が欠けている場合は判定せず、不足分を返します。

```bash
python3 scripts/check.py 文章.md --json | python3 scripts/overlap_judgement.py --from-check
```

終了コードは 0（修正不要）、1（修正が必要）、2（入力不足）です。しきい値は `--min-kinds` と `--star-min` で変更できます。テストは `tests/test_overlap_judgement.py` です。
