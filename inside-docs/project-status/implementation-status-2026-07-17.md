# Excel2TeX 実装状況

- 基準日: 2026-07-17
- 対象コミット: `6472240`（Grid toolbar / UI layout update）
- 追加対象: コミット後の Table Preview 性能最適化ワークツリー

## 1. 概要

Excel2TeX は、CSV/XLSX の表を読み込み、画面上で編集・整形したうえで LaTeX の表へ
変換できる Flet デスクトップアプリです。ファイル読込、TeX 変換、プレビュー、コピー、
詳細な出力設定、データ前処理、セル結合を含む表編集、Undo/Redo、`.tex` 保存まで
実装済みです。

今回の更新では、3 ペイン画面の UI/UX を整理し、Input、Operations、Table Preview、
Generated TeX の各操作をカラム幅に合わせて再配置しました。また、大規模テーブルで
Table Preview の更新が遅くなる問題に対し、履歴コピー、スクロール、Style 更新、
セル編集後の TeX 再生成を最適化しました。

静的検査と 270 件の自動テストは成功しています。GUI の自動 E2E テストと全対象 OS
での手動スモークテストは継続課題です。

## 2. 実装済み機能

### 2.1 入出力

- `.csv` / `.xlsx` ファイルの読み込み
- 先頭の空行と先頭の空列を除外した読込データの正規化
- 読み込み中の進捗バーとステータスメッセージ
- ファイル解析の UI スレッド外実行
- 生成した TeX の読み取り専用プレビュー
- クリップボードへのコピー
- `.tex` ファイルとしての保存
- 空データ、未対応拡張子、読込・保存失敗時のエラー表示

### 2.2 LaTeX 変換

- `table` と `tabular` の基本出力
- `longtable` / `tabularx` の選択
- キャプションとラベル
- 表全体の配置、セル文字列の既定配置、セル単位の配置上書き
- 罫線スタイル: `all` / `booktabs` / `horizontal` / `none`
- 先頭行・先頭列の太字化
- LaTeX 特殊文字のエスケープ切替
- `[htbp]` フロート位置指定の切替
- スケール係数による `\resizebox` 出力
- 単体でコンパイル可能な完全な文書の出力
- 結合セルに対する `\multicolumn` / `\multirow` と部分罫線の生成
- 選択機能に応じた `booktabs`、`longtable`、`tabularx`、`graphicx`、
  `multirow` パッケージの追加

### 2.3 表データの編集

- セル内容の直接編集
- 単一セル選択と矩形範囲選択
- セルの結合・分離
- 行・列の上下左右への挿入
- 行・列の削除
- セル単位の左寄せ・中央寄せ・右寄せ・既定値継承
- Undo / Redo（最大 50 スナップショット）
- 大規模表で可視行付近のみを描画するウィンドウイング
- 表示範囲をまたぐ結合セルの描画維持

### 2.4 前処理

- 転置
- 全セルが空の行・列の削除
- 重複行の削除
- 読み込み直後の状態へのリセット

結合セルを保持したままの前処理には未対応であり、結合が存在する場合は前処理を
ブロックします。

### 2.5 UI/UX

#### Input カラム

- Input と Operations を独立したパネルとして表示
- Input 見出し、ファイル選択、選択ファイル名、進捗バーを同じ枠内に配置
- Input、Operations、各設定パネルを左カラム幅いっぱいに配置
- Operations の 4 操作を 2 列 × 2 行で配置
- Additional Info の Caption / Label を縦 2 行で配置
- Scale box を独立した全幅行で配置
- Full document、Float position、Bold first row / column を Switch 化
- Bold first row / column を縦 2 行で配置
- パネル見出しを `TITLE_MEDIUM` に統一
- ログテキストを 3 ペイン外の画面最下部へ移動し、枠線を削除

#### Table Preview

- ツールバーを `Edit` / `Cells` / `Rows` / `Columns` の 4 グループに整理
- `Edit` と `Cells`、`Rows` と `Columns` をそれぞれ横並びで表示
- 各グループを均等幅にし、Table Preview カラム幅いっぱいに配置
- Undo/Redo、範囲選択、結合・分割、行列操作をアイコンボタン化
- 全アイコンにツールチップを付与
- 行列挿入を `+↑` / `+↓` / `←+` / `+→` で方向付き表示
- Cell alignment は内容を明示する Dropdown を維持

#### Generated TeX

- Copy / Download ボタンを均等幅でカラム幅いっぱいに配置
- TeX プレビューをカラム残り領域へ展開

### 2.6 配布

- Flet の `src` レイアウトによるローカル起動・ビルド設定
- `ver.X.Y.Z` 形式のタグを契機とする GitHub Actions リリースフロー
- Windows / macOS / Linux のビルドと成果物パッケージ化
- 3 OS の成果物を添付したドラフト GitHub Release の作成

## 3. 大規模テーブル向け性能最適化

### 3.1 Undo/Redo スナップショット

- 汎用 `copy.deepcopy()` を `clone_grid()` に置換
- Cell の既知フィールドだけを直接コピーし、独立性と結合情報を維持
- Reset 時の Grid コピーにも同じ専用処理を使用
- DataFrame の復元は `copy(deep=True)` を使用

2,000 行 × 50 列の同一プロセス比較では、スナップショット生成が約 10.9 倍
高速化しました。数値は開発環境上の参考値であり、端末条件により変動します。

### 3.2 Table Preview の Style 更新

- Border style、Bold、Text alignment の変更時に GridEditor を再生成しない
- 表示中の TextField の Style、Alignment、Border だけを差分更新
- 選択状態とスクロール位置を維持

同じ 2,000 行 × 50 列の比較では、Style 更新が約 5.9 倍高速化しました。

### 3.3 スクロール時のウィンドウイング

- 下方向スクロール時に先頭行から表示範囲までを毎回走査する処理を廃止
- 現在の可視行と、可視範囲上端をまたぐ結合セルの Anchor だけを処理
- 行数が増えても、過去の非表示行数に比例して走査量が増えない構造へ変更

### 3.4 セル編集時の更新

- キー入力ごとに Grid 内容は即時更新
- TeX 全体の再生成とページ更新はセルからフォーカスが外れた時にまとめて実行
- 大規模表での連続入力中に、TeX 全体再生成が毎キー発生することを防止

## 4. 現在の構成

```text
Excel2TeX/
├── src/
│   ├── main.py             # Flet UI、状態管理、イベント統合
│   ├── ui_layout.py        # 共通寸法と設定パネル Builder
│   ├── converter.py        # DataFrame から LaTeX への変換とファイル読込
│   ├── preprocessing.py    # DataFrame 前処理
│   ├── table_model.py      # Cell / TableGrid、構造編集、専用 Grid コピー
│   ├── grid_converter.py   # TableGrid から LaTeX への変換
│   ├── grid_editor.py      # 表プレビュー、セル編集、差分 Style 更新
│   ├── grid_toolbar.py     # グループ化した表編集ツールバー
│   ├── grid_history.py     # Undo / Redo 履歴
│   └── assets/icon.png     # アプリアイコン
├── tests/                  # 7 モジュールの pytest テスト
├── inside-docs/            # 仕様、履歴、現況資料
├── .github/workflows/      # リリースビルド
├── pyproject.toml          # 依存関係と pytest / ruff / Flet 設定
├── uv.lock                 # 依存関係ロック
└── README.md               # 開発・実行方法
```

### 主要モジュールの責務

| モジュール | 責務 |
|---|---|
| `main.py` | 3 ペイン UI、ファイル選択、オプション状態、各ロジックの接続 |
| `ui_layout.py` | UI 寸法と共通設定パネルの生成 |
| `converter.py` | DataFrame 系の変換、変換オプション、特殊文字処理、CSV/XLSX 読込 |
| `table_model.py` | 編集用 Grid、構造操作、高速な独立コピー |
| `grid_converter.py` | 編集済み Grid と結合情報を LaTeX へ変換 |
| `grid_editor.py` | 選択、直接編集、描画、差分 Style 更新、ウィンドウイング |
| `grid_toolbar.py` | 結合・分離・挿入・削除・配置・履歴操作の UI |
| `grid_history.py` | `clone_grid()` スナップショットによる Undo / Redo |
| `preprocessing.py` | 元データを変更しない DataFrame 前処理 |

UI と変換・データモデルのロジックは分離され、Flet を起動せずに主要ロジックを
テストできる構成です。

## 5. 検証状況

2026-07-17 にワークツリー上で以下を実行しました。

| 検証 | 結果 |
|---|---|
| `uv run ruff check .` | 成功（`All checks passed!`） |
| `uv run ruff format --check .` | 成功（16 files already formatted） |
| `uv run pytest -q` | 成功（270 passed、10.62 秒） |

自動テストは次の領域をカバーしています。

- DataFrame の読込、正規化、LaTeX 変換と各出力オプション
- 表 Grid の生成、セル結合・分離、行列の挿入・削除、配置
- 結合セルを含む LaTeX 変換
- セル選択、編集確定、ツールバー、表示 Style、ウィンドウイング
- 可視範囲をまたぐ結合セルと、非表示過去行を走査しないスクロール処理
- Undo / Redo の履歴操作、上限、専用 Grid コピーの独立性
- 共通設定パネルの見出しと Stretch 配置
- 転置、空行列削除、重複削除

## 6. 既知の制約と残課題

優先度が高いものから記載します。

1. **GUI の実機確認**
   自動テストはロジックと UI 部品の単体動作が中心です。ファイル選択、進捗表示、
   3 ペイン配置、セル編集、スクロール、Undo/Redo、コピー、保存を実際の Flet
   ウィンドウで一巡させる手動スモークテストが必要です。

2. **横方向の大規模表**
   行方向はウィンドウイングされていますが、列方向は全列分の表示 Control を生成します。
   列数が非常に多い表では、横方向ウィンドウイングを追加する余地があります。

3. **Undo/Redo のメモリ効率**
   コピー処理は高速化しましたが、履歴は引き続き Grid 全体を最大 50 件保持します。
   非常に大きな表では差分履歴方式を検討できます。

4. **結合セルと前処理の統合**
   転置、空行列削除、重複削除は DataFrame ベースです。結合済み Grid への適用は
   未実装で、現在は誤った変換を避けるため操作をブロックします。

5. **編集・スクロールの細部**
   編集中セルがスクロールで描画範囲外になる場合のフォーカス維持や、構造変更後の
   スクロール位置維持には改善余地があります。

6. **モジュールサイズ**
   `main.py` は 763 行、`grid_editor.py` は 974 行です。`grid_editor.py` はプロジェクトの
   目安である 800 行を超えており、今後の拡張前にセル描画、選択、ウィンドウイングの
   分割を検討する必要があります。

## 7. 実行方法

```powershell
uv sync
uv run flet run src/main.py
```

品質確認:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Windows 向けローカルビルド:

```powershell
uv run flet build windows -vv
```

## 8. ドキュメントの位置づけ

- この文書は、コミット `6472240` と直後の性能改善ワークツリーを基準にした現況です。
- `mvp-implementation/`、`additional-info-feature/`、`extended-features/`、
  `table-editor-feature/` の報告書は実装経緯を示す履歴資料です。
- 過去資料に記載されたテスト件数、ファイル配置、未実装項目は、その資料作成時点の情報です。
- 次回は `project-status/` に新しい日付の文書を追加し、実装の変遷を残します。
