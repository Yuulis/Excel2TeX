# テーブルエディター機能 実装報告

対象: Excel2TeX インタラクティブ・テーブルエディター（セル結合・分離 / セル内容編集 / 行・列の挿入・削除 / セル単位の配置指定 / Undo・Redo / 大規模テーブル描画最適化）
実装期間: 2026-07-10（フェーズ A〜C）〜 2026-07-11（UI・性能フォローアップ）
関連設計: `.claude/docs/research/table-editor-design.md`（アーキテクチャ設計書）

## 1. 結論

読み込んだテーブルに対して、UI 上でセルの結合・分離をはじめとする各種編集を行える機能を新設した。
これは MVP の「結合セルは扱わない」という当初スコープを覆す拡張であり、DataFrame では表現できない
結合セルを扱うために **セル・グリッドのデータモデル**（`TableGrid` / `Cell`）を新規導入している。

- `uv run pytest -q`: **240 passed**（拡張機能フェーズ時点の 50 → 240、+190 件）
- `uv run ruff check .` / `ruff format --check .`: クリーン
- `import main` / 各モジュール: OK
- 主要環境: Python（uv 管理）/ pandas 3.x / Flet 0.85.3
- ⚠️ GUI のエンドツーエンド動作は未検証（Flet はヘッドレス実行不可）。pytest とインポートによる検証のみ。

## 2. アーキテクチャ概要

| ファイル | 行数 | 役割 |
|---|---:|---|
| `table_model.py` | 356 | データモデル。`Cell`（dataclass）/ `CellAlignment`（enum）/ `TableGrid`（結合・分離・挿入・削除・配置の純粋ロジック）/ `dataframe_to_grid()` |
| `grid_converter.py` | 340 | `grid_to_latex(grid, options)`。結合を含むグリッドから LaTeX を生成（`\multicolumn` / `\multirow` / `\cline`） |
| `grid_editor.py` | 683 | Flet 製カスタムグリッド UI（`GridEditor`）。選択・編集・ビューポート・ウィンドウイング |
| `grid_toolbar.py` | 335 | ツールバー（結合・分離・挿入・削除・配置・Undo・Redo）の構築 |
| `grid_history.py` | 89 | Undo / Redo の純粋ロジック（`GridHistory`、deepcopy スナップショット） |
| `main.py` | 689 | Flet GUI 統合。3 ペインレイアウト・状態管理・各コールバック |
| `converter.py` | 388 | 既存の DataFrame → LaTeX 変換。**Flet 非依存を維持**（`grid_converter` が `ConversionOptions` とエスケープを再利用） |

**設計判断（最重要）**: 結合セルの表現方式として、**「Cell のグリッド」モデル** を採用した
（対抗案の「DataFrame ＋ 結合領域リスト」は不採用）。各 `Cell` が `colspan` / `rowspan` /
`alignment` / `is_covered`（結合で覆われたセルか）/ `anchor_row` / `anchor_col` を持ち、
グリッド全体が二次元の真実の情報源となる。詳細な比較検討は設計書 §（`.claude/docs/research/table-editor-design.md`）を参照。

---

## 3. フェーズ A: データモデル・コンバータ（純粋ロジック層）

### 3.1 `table_model.py`
- `Cell`（dataclass）: `content` / `colspan` / `rowspan` / `alignment` / `is_covered` / `anchor_row` / `anchor_col`
- `CellAlignment`（enum）: `l` / `c` / `r` / `inherit`（= `None`、列既定を継承）
- `TableGrid` 主要メソッド:
  - `get_cell` / `set_content`
  - `merge_cells` / `split_cell` / `validate_merge`（矩形性・既存結合との衝突を検証）
  - `insert_row` / `insert_col` / `delete_row` / `delete_col`（結合をまたぐ挿入・削除も整合を維持）
  - `set_alignment`
- `dataframe_to_grid()`: 読み込んだ DataFrame（ヘッダー＋本文）をグリッドへ変換

### 3.2 `grid_converter.py`
- `grid_to_latex(grid: TableGrid, options: ConversionOptions) -> str`
- 既存 `converter.py` の `ConversionOptions` とエスケープ処理を再利用（重複実装なし）
- 水平結合 → `\multicolumn{n}{spec}{content}` / 垂直結合 → `\multirow{n}{*}{content}`
- 垂直結合の下は部分罫線（`\cline` / booktabs 時は `\cmidrule`）で分割
- セル単位の配置は `\multicolumn{1}{spec}{content}` で 1 セルのみ上書き
- `multirow` パッケージは MWE モード時に必要に応じて自動挿入

### 3.3 フェーズ A で発見・修正した設計書のバグ
1. `_multicolumn_spec` が列 0 のときだけ左罫線を付けていた → `\multicolumn` は左罫線を置換するため、`border_style="all"` では常に `|letter|` を出力するよう修正
2. `insert_row` に未定義変数 `r` があった → クリーンな逐次パスで書き直し
3. `_determine_rules` の優先順位不備 → `is_last` を `is_header` より優先し、booktabs の単一行出力を正しく生成

---

## 4. フェーズ B: 読み取り専用グリッド描画

- Flet の `ft.Stack` に **絶対座標配置** でセルを描画（結合セルの跨ぎ表示を実現するため、
  DataTable ではなくカスタムグリッドを採用）
- 定数: `CELL_WIDTH = 120` / `CELL_HEIGHT = 40`
- この段階では表示のみ（編集操作は次フェーズ）

---

## 5. フェーズ C: 編集操作

### C1: 選択とセル内容の直接編集
- 選択状態（`_selection_start` / `_selection_end` / `_selected_row` / `_selected_col`）と範囲選択モード
- `apply_edit` によるセル内文字列の直接編集
- **フォーカス保持設計**: 編集中（`_on_cell_edit`）はエディタを再構築せず、TeX 出力の再生成と
  `page.update()` のみ実行 → 入力中に TextField のフォーカスが外れない
- Flet が shift 修飾キーによる範囲選択に対応しないため、明示的な「Range Select」トグルボタンで代替

### C2: セルの結合・分離
- `merge_selection` / `split_selection`（`TableGrid` の検証ロジックを呼び出し）
- 水平・垂直の両方の結合に対応

### C3: 行・列の挿入・削除 / セル単位の配置 / 前処理ガード
- `insert_row_above` / `insert_row_below` / `insert_col_left` / `insert_col_right` / `delete_row` / `delete_col`
- `set_selected_alignment`（選択セルの配置を `l` / `c` / `r` / 継承 に設定）
- 前処理（転置・ケース変換等）は結合が存在する場合ブロック（前処理はグリッド非対応のため）

---

## 6. フォローアップ（2026-07-11）: UI・性能・Undo/Redo

ユーザー要望に基づく 4 項目を実装した。

### 6.1 3 ペイン中央レイアウト
- Table Preview が左に寄って狭かった問題を解消
- 左（入力・オプション、`expand=2`）／ **中央（Table Preview、`expand=4` で最大幅）** ／
  右（生成 TeX、`expand=3`）の 3 ペイン構成

### 6.2 配置ドロップダウンの選択セル反映
- セル選択時に `on_selection_change` 経由でドロップダウンの表示値を選択セルの現在値へ更新
- 値更新が編集イベントを誘発するフィードバックループは `_programmatic_update` フラグで抑止

### 6.3 Undo / Redo（`grid_history.py` を新設）
- `GridHistory`（純粋ロジック）: `push` / `undo` / `redo` / `clear` / `discard_last` / `can_undo` / `can_redo`
- deepcopy スナップショット方式、上限 `MAX_HISTORY = 50`
- 結合・分離・挿入・削除・配置・前処理は変更前スナップショットを 1 本のパスで記録
- **テキスト編集は編集セッション単位でコアレス** → 1 回の Undo でそのセルの入力全体を戻す
  （キーストロークごとには戻さない）
- Reset で履歴をクリア

### 6.4 大規模テーブルの描画性能（ビューポート・ウィンドウイング）
- 従来は `ft.Stack` が全セルを描画（500 行 × 10 列で 5000 コントロール）
- **絶対座標 Stack モデルを維持したまま**、可視行＋オーバースキャン分のみ描画するよう最適化
  （結合の跨ぎ表示を壊さない）
- 純粋関数として切り出し・テスト:
  - `should_use_windowing()`
  - `compute_visible_row_range(total_rows, row_height, viewport_top, viewport_height, overscan_rows)`
  - `cell_visible_in_row_range(cell_row, cell_rowspan, visible_first, visible_last)`（結合が境界を跨ぐケースを含む）
  - `handle_scroll()` / `_build_cell_controls_for_range()`
- Flet の `OnScrollEvent`（`pixels` / `viewport_dimension`）で可視範囲変化時のみ再描画
- 定数: `VIRTUALIZE_ROW_THRESHOLD = 50`（50 行未満は従来どおり全描画で挙動不変）/
  `VIEWPORT_OVERSCAN_ROWS = 5` / `DEFAULT_VIEWPORT_HEIGHT = 800.0`
- 効果: 500 行規模で 5000 → 約 50〜80 コントロールに削減

---

## 7. `main.py` の統合

- 状態: `state["grid"]` / `["original_grid"]` / `["editor"]` / `["edit_session_cell"]`
- 主要ハンドラ: `_on_cell_edit`（TeX 再生成のみ、フォーカス保持）/ `_refresh_grid_view` /
  `_on_grid_change` / `_on_selection_change` / `_record_history` / `_discard_last_history` /
  `_grid_has_merges` / `_apply_preprocessing`（結合時ガード）/ `_on_grid_scroll`
- 中央ペインの `grid_scroll_column` に `on_scroll` を接続し、ウィンドウイングを駆動

---

## 8. テスト

| テストファイル | 行数 | 内容 |
|---|---:|---|
| `tests/test_table_model.py` | 521 | Cell / TableGrid の結合・分離・挿入・削除・配置・検証 |
| `tests/test_grid_converter.py` | 492 | `grid_to_latex`（multicolumn / multirow / cline / セル配置 / 罫線スタイル） |
| `tests/test_grid_editor.py` | 1106 | 選択・編集・結合・分離・挿入削除・配置・ウィンドウイング純関数（可視範囲・結合跨ぎ含む） |
| `tests/test_grid_history.py` | 295 | `GridHistory`（push / undo / redo / clear / discard_last / コアレス / 上限） |

合計 **240 passed**。`ruff check` / `ruff format --check` クリーン。

---

## 9. 残課題・留意点（既知の制約）

- **GUI 実機スモーク未実施**: `uv run python main.py` で 3 ペイン・スクロール・結合・Undo/Redo を
  手動確認する必要がある（ヘッドレス自動検証不可）。大規模表は次で生成可能:
  `python -c "import pandas as pd; pd.DataFrame({f'c{i}': range(200) for i in range(5)}).to_csv('big.csv', index=False)"`
- **前処理が結合非対応**: 結合が存在する間は前処理をブロックしたまま（グリッド対応は未実装）
- **画面外セルのフォーカス**: 編集中のセルがスクロールで窓外に出るとフォーカスが外れる
- **構造変更後のスクロール**: 挿入・削除の後にビューが先頭へ戻る場合がある（次スクロールで解消）
- **Undo のメモリ効率**: 現状は deepcopy 全体スナップショット。差分ベース Undo は将来最適化候補
- **ファイルサイズ**: `main.py` 689 行 / `grid_editor.py` 683 行と目安（200〜400 行、上限 800）超過。
  今後の機能追加時はウィンドウイング純関数を `grid_windowing.py` へ抽出するリファクタを推奨
- **未コミット**: 本機能一式は 2026-07-11 時点で git 未コミット（GUI 手動確認後にコミット予定）

---

## 10. 補足: 実装体制

CLAUDE.md のオーケストレーター契約では設計・実装を Codex CLI へ委譲する方針だが、
本機能の実装期間中、インストール済み Codex CLI（v0.114.0）が想定モデル（`gpt-5.5`）を実行できず
利用不能だった。そのため設計・実装は Opus の `general-purpose` サブエージェントへ委譲して進めた
（詳細はメモリ `codex-cli-unavailable` を参照）。
