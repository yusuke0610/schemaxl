## 概要

<!-- 何を・なぜ変えたか。再現できる不具合なら修正前 / 修正後の挙動も。 -->

## 関連 issue

<!-- Closes #123 / Refs #123 -->

## 変更点

-

## 設計上の判断

<!-- solver(純粋関数)/ PlacementPlan(純データ)/ backend(副作用のみ)の分離に触れる変更なら、その扱いを書く。 -->

## 確認したこと

- [ ] `ruff check .` / `ruff format --check .`
- [ ] `mypy`
- [ ] `pytest --cov`(core 95% / backends 85% 以上)
- [ ] solver 層のテストに I/O・openpyxl を持ち込んでいない
- [ ] 公開 API が変わる場合、README の「API スケッチ」を更新した
- [ ] `CHANGELOG.md` の Unreleased に追記した

## 後方互換

<!-- 既存の書き方で挙動が変わるケースがあれば列挙する。無ければ「なし」。 -->
