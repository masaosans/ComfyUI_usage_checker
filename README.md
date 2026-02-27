# ComfyUI Usage Checker

ComfyUIの workflow を横断スキャンし、  
**未使用の models / custom_nodes を検出するツール**です。

- NODE_CLASS_MAPPINGS + INPUT_TYPES の動的解析
- Embedding対応
- 依存関係解析（Dependency Graph）
- モデルカテゴリ自動判定
- 再帰スキャン対応

を実装しています。

---

# 主な機能

## 1. Workflow一括スキャン
指定ディレクトリ配下の全 `.json` workflow を再帰的に解析。

## 2. Models 全カテゴリ再帰スキャン
ComfyUIの `folder_paths` を使用して：

- checkpoints
- loras
- vae
- controlnet
- clip
- embeddings
- unet
- その他拡張カテゴリ

を自動検出。

## 3. Custom Nodes 再帰解析
`custom_nodes` ディレクトリを再帰スキャンし、
使用・未使用を判定。

## 4. Precise Model Detection Mode（動的解析）

固定node_type依存ではなく：

- `NODE_CLASS_MAPPINGS`
- 各ノードの `INPUT_TYPES()`
- `"folder"` 指定
- MODEL系型判定
- キーワードヒューリスティック

を組み合わせた多層検出。

将来の custom_nodes 追加にも自動適応します。

## 5. Embedding対応

以下形式を検出：

```
embedding:xxx
<embedding:xxx>
```

`.pt`自動補完対応。

##  6. 依存関係解析（Dependency Graph）

- ノード → モデル依存関係
- 使用ノード数
- 使用モデル数

をレポート出力。

---

# インストール

1. git clone
```
git clone https://github.com/masaosans/ComfyUI_usage_checker.git
```
2. ComfyUI再起動

---

#  使い方

1. ノード追加　→　`check usage model and node` を配置
2. `workflow_dir` に workflow フォルダを指定

#  出力例

```
===== USAGE REPORT =====

---- Used Custom Nodes ----
MyCustomNode (C:\ComfyUI\custom_nodes\MyCustomNode)

---- Unused Custom Nodes ----
OldNode (C:\ComfyUI\custom_nodes\OldNode)

---- Used Models ----
dreamshaper.safetensors (C:\ComfyUI\models\checkpoints\dreamshaper.safetensors)

---- Unused Models ----
unused_model.safetensors (C:\ComfyUI\models\checkpoints\unused_model.safetensors)

---- Dependency Summary ----
Used Nodes: 42
Used Models: 18
```

---

#  技術仕様

## モデル検出優先順位

1. INPUT_TYPES内 `"folder"` 指定
2. MODEL / CLIP / VAE 等の型判定
3. 入力名ヒューリスティック
4. 拡張子フォールバック検出

多層構造で漏れを最小化。

---

# 注意事項

- 削除は自動では行いません
- 実行中workflowは検出対象外
- Embedding名とファイル名が一致しない場合は手動確認推奨

---

# このツールの思想

拡張子検索ではなく、  
ComfyUIの内部構造に沿った解析で

**将来耐性のある Usage Checker を実現する**

ことを目的としています。

---

#  ライセンス

MIT License
