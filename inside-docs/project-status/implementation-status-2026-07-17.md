# Excel2TeX 実装状況

基準日: 2026-07-17  
対象コミット: `80a92ab`（Refactor code structure for improved readability and maintainability）

## 1. 概要

Excel2TeX は、CSV/XLSX の表を読み込み、画面上で編集・整形したうえで LaTeX の表へ
変換できる Flet デスクトップアプリとして実装されています。当初の MVP に含まれていた
ファイル読込、TeX 変換、プレビュー、コピーに加え、詳細な出力設定、データ前処理、
セル結合を含む表編集、Undo/Redo、`.tex` 保存まで実装済みです。

2026-07-17 時点では静的検査と自動テストは成功しています。一方、GUI を操作する
エンドツーエンドの自動テストと、全対象 OS での手動スモークテストは継続課題です。

## 2. 実装済み機能

### 2.1 入出力

- `.csv` / `.xlsx` ファイルの読み込み
- 先頭の空行と先頭の空列を除外した読込データの正規化
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
- 単体でコンパイル可能な MWE（完全な文書）出力
- 結合セルに対する `\multicolumn` / `\multirow` と部分罫線の生成
- 選択機能に応じた `booktabs`、`longtable`、`tabularx`、`graphicx`、
  `multirow` パッケージの MWE への追加

### 2.3 表データの編集

- セル内容の直接編集
- 単一セル選択と矩形範囲選択
- セルの結合・分離
- 行・列の上下左右への挿入
- 行・列の削除
- セル単位の左寄せ・中央寄せ・右寄せ・既定値継承
- Undo / Redo（最大 50 スナップショット）
- 大規模表で可視行付近のみを描画するウィンドウイング

### 2.4 前処理

- 転置
- 全セルが空の行・列の削除
- 重複行の削除
- 読み込み直後の状態へのリセット

結合セルを保持したままの前処理には未対応であり、結合が存在する場合は前処理を
ブロックする設計です。

### 2.5 配布

- Flet の `src` レイアウトによるローカル起動・ビルド設定
- `ver.X.Y.Z` 形式のタグを契機とする GitHub Actions リリースフロー
- Windows / macOS / Linux のビルドと成果物パッケージ化
- 3 OS の成果物を添付したドラフト GitHub Release の作成

## 3. 現在の構成

```text
Excel2TeX/
├── src/
│   ├── main.py             # Flet UI、状態管理、イベント統合
│   ├── ui_layout.py        # 画面レイアウト共通定数
│   ├── converter.py        # DataFrame から LaTeX への変換とファイル読込
│   ├── preprocessing.py    # 非破壊の DataFrame 前処理
│   ├── table_model.py      # Cell / TableGrid と構造編集ロジック
│   ├── grid_converter.py   # TableGrid から LaTeX への変換
│   ├── grid_editor.py      # 表プレビュー・セル編集 UI
│   ├── grid_toolbar.py     # 表編集ツールバー
│   ├── grid_history.py     # Undo / Redo 履歴
│   └── assets/icon.png     # アプリアイコン
├── tests/                  # 6 モジュールの pytest テスト
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
| `converter.py` | DataFrame 系の変換、変換オプション、特殊文字処理、CSV/XLSX 読込 |
| `table_model.py` | 結合セルを表現できる編集用グリッドと構造操作 |
| `grid_converter.py` | 編集済みグリッドと結合情報を LaTeX へ変換 |
| `grid_editor.py` | 選択、直接編集、描画、スクロール時のウィンドウイング |
| `grid_toolbar.py` | 結合・分離・挿入・削除・配置・履歴操作の UI |
| `grid_history.py` | deepcopy スナップショットによる Undo / Redo |
| `preprocessing.py` | 元データを変更しない DataFrame 前処理 |

UI と変換・データモデルのロジックは分離されており、Flet を起動せずに主要ロジックを
テストできる構成です。

## 4. 検証状況

2026-07-17 にワークツリー上で以下を実行しました。

| 検証 | 結果 |
|---|---|
| `uv run ruff check .` | 成功（`All checks passed!`） |
| `uv run pytest -q` | 成功（263 passed、7.56 秒） |

自動テストは次の領域をカバーしています。

- DataFrame の読込、正規化、LaTeX 変換と各出力オプション
- 表グリッドの生成、セル結合・分離、行列の挿入・削除、配置
- 結合セルを含む LaTeX 変換
- セル選択、編集、ツールバー、表示スタイル、ウィンドウイング
- Undo / Redo の履歴操作と上限
- 転置、空行列削除、重複削除

## 5. 既知の制約と残課題

優先度が高いものから記載します。

1. **GUI の実機確認**  
   自動テストはロジックと UI 部品の単体動作が中心です。ファイル選択、コピー、保存、
   3 ペイン表示、セル編集、スクロール、Undo/Redo を実際の Flet ウィンドウで一巡させる
   手動スモークテストが必要です。

2. **結合セルと前処理の統合**  
   転置、空行列削除、重複削除は DataFrame ベースです。結合済みグリッドへの適用は
   未実装で、現在は誤った変換を避けるため操作をブロックします。

3. **大規模表編集の細部**  
   編集中セルがスクロールで描画範囲外になる場合のフォーカス維持や、構造変更後の
   スクロール位置維持には改善余地があります。

4. **Undo/Redo のメモリ効率**  
   履歴はグリッド全体の deepcopy を保存します。非常に大きな表では差分方式への移行を
   検討できます。

5. **モジュールサイズ**  
   `main.py` と `grid_editor.py` は責務が増えており、今後の拡張前にイベント処理、
   ウィンドウイング、UI セクションなどの追加分割を検討する余地があります。

6. **未着手または仕様再確認が必要な機能**  
   キャプションの表上部・下部の切替、結合を保持した前処理など、拡張仕様に記載されつつ
   現在の UI に存在しない項目があります。次フェーズ開始時に仕様の優先順位を再確認する
   必要があります。

## 6. 実行方法

```powershell
uv sync
uv run flet run src/main.py
```

品質確認:

```powershell
uv run ruff check .
uv run pytest
```

Windows 向けローカルビルド:

```powershell
uv run flet build windows -vv
```

## 7. ドキュメントの位置づけ

- この文書は、コードとテストを基準にした 2026-07-17 時点の現況スナップショットです。
- `mvp-implementation/`、`additional-info-feature/`、`extended-features/`、
  `table-editor-feature/` の報告書は実装経緯を示す履歴資料です。
- 過去資料に記載されたテスト件数、ファイル配置、未実装項目は、その資料作成時点の情報です。
- 次回更新時は、このファイルを上書きせず `project-status/` に新しい日付の文書を追加すると、
  実装の変遷を追跡できます。

