# frontier-radar

A self-expanding scanner for the **edges of the internet**. It surfaces things
far from the algorithmic centre — individual blogs, pre-viral posts, edge-of-field
research, experimental work — and, crucially, **grows its own list of sources over
time** instead of reading a fixed feed.

> レコメンドは「過去へのタイムマシン」。中央は必ず腐る。これは中央から最も遠いものを毎日自動で拾い、
> 情報源そのものを自己増殖・自己淘汰させ続けるための装置。

## なぜ普通のRSSリーダーと違うのか

情報源を固定しないための機構を、内部構造に埋め込んである（`pipeline/discovery.py`）:

1. **共引用ディスカバリー** — 信頼できるソースと反アルゴリズム系アグリゲータ
   （Hacker News の新着、arXiv、Lobsters、Are.na）が繰り返しリンクする外部ドメインを
   候補として追跡。閾値（既定は2つの別ソースから被リンク）を超えると、RSS/Atomを
   **自動検出**して `trial` ソースに昇格する。*辺境は辺境にリンクする。*
2. **自己淘汰** — 各ソースの「辺境スコア」平均を記録。良い `trial` は `active` に昇格、
   劣化したものは `retired` に。リストが自分で自分を手入れする。
3. **ε-探索** — 毎回わざと未知・低データ・引退済みのソースを混ぜる。決定論が停滞の正体なので、
   構造的に揺らぎを入れて固定化を防ぐ。

`config/seeds.yaml` の seed は**出発点にすぎない**。手で足してもいいし、放っておいても勝手に広がる。

## 辺境スコア

「アルゴリズムの中央からどれだけ遠いか」を 0〜1 の数字に。加点/減点の理由は全アイテムに表示される
（`pipeline/scoring.py`。感覚でチューニング可能）:

- **加点**: 個人/辺境ドメイン、バイラル前（HNの低スコア）、希少なソース、実験・エッセイ語彙、
  言語裁定（英語圏フィードでのCJKなど）、新鮮さ。
- **減点**: 大手ドメイン、既にバズり済み、煽り/リスティクル語彙。
- 決定論を避けるための微小な乱数ジッタ入り。

## ローカル実行

```bash
pip install -r requirements.txt
python -m pipeline.run
```

生成物:
- `site/data/digest.json` — その日のランキング
- `site/data/sources.json` — 生きているソースプール（増殖・淘汰の履歴つき）
- `data/*.json` — システムの**記憶**（コミットして次回に持ち越す）

サイトを見る（静的なので何でも可）:

```bash
python -m http.server -d site 8000
```

→ http://localhost:8000

## GitHub で毎日動かす

1. このフォルダを **public リポジトリ** として push（機密は `.gitignore` 済み）。
2. Settings → Pages → **Source: GitHub Actions**。
3. （任意）Settings → Secrets and variables → Actions に `ANTHROPIC_API_KEY` を追加すると、
   各アイテムに日本語の一言ブラーブが付く。無くても動く。
4. `.github/workflows/daily.yml` が毎朝 07:00 JST に実行し、
   進化したソース記憶をリポジトリにコミットし、サイトを公開する。

## 機密情報

git 管理外（`.gitignore`）:
- `.env` / `.env.*` — APIキー等。GitHub では repo secrets を使う。

`data/*.json` は**意図的にコミット対象**。これはシステムの記憶であり、これが無いと毎回リセットされて
「増殖」しない。機密ではない（公開URLと統計のみ）。

## ディレクトリ

```
config/     seeds.yaml（出発点）, mainstream.txt（中央＝減点対象）
pipeline/   fetchers / scoring / discovery / summarize / render / run
data/       進化する記憶（sources / candidates / seen）
site/       静的サイト（GitHub Pages）
```

## 育て方

- 気になる個人ブログを見つけたら `config/seeds.yaml` の `seeds:` に一行足すだけ。
- `retire_below_avg` や `explore_fraction` などの挙動は `seeds.yaml` の `settings:` で調整。
- スコアの効き方は `pipeline/scoring.py` の `EDGE_WORDS` / `HYPE_WORDS` を書き換えて感覚で。
