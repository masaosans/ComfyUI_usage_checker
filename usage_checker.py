import os
import json
import re
import folder_paths
from nodes import NODE_CLASS_MAPPINGS


class UsageCheckerNode:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_dir": ("STRING", {"default": "user/default/workflows"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "utils"

    # =====================================================
    # メイン処理
    # =====================================================

    def run(self, workflow_dir):

        workflow_dir = os.path.abspath(workflow_dir)

        used_node_types = set()
        used_model_files = set()
        dependency_graph = {}

        # 🔥 全workflowスキャン
        for root, _, files in os.walk(workflow_dir):
            for file in files:
                if not file.endswith(".json"):
                    continue
                if file.startswith("."):
                    continue  # ← これ重要
        
                self.scan_workflow(
                    os.path.join(root, file),
                    used_node_types,
                    used_model_files,
                    dependency_graph
                )
        # custom_nodes
        custom_nodes_dir = folder_paths.get_folder_paths("custom_nodes")[0]

        # 🔥 custom_nodes直下のみ取得
        top_level_dirs = self.get_top_level_custom_nodes(custom_nodes_dir)

        # 🔥 モデル一覧
        all_models = self.scan_all_model_files()

        # node_type → path
        node_type_to_path = self.build_node_type_path_map(custom_nodes_dir)

        used_node_paths = set(
            node_type_to_path.get(nt)
            for nt in used_node_types
            if nt in node_type_to_path
        )

        unused_models = set(all_models.keys()) - used_model_files

        # 🔥 削除可能ディレクトリ判定
        removable_dirs = self.detect_removable_directories(
            top_level_dirs,
            node_type_to_path,
            used_node_types
        )

        # ===== レポート =====
        report = []
        report.append("===== USAGE REPORT =====\n")

        report.append("---- Used Custom Nodes ----")
        for nt in sorted(used_node_types):
            path = node_type_to_path.get(nt, "")
            report.append(f"{nt} ({path})")

        report.append("\n---- Removable Custom Node Directories ----")
        for d in sorted(removable_dirs):
            report.append(f"{os.path.basename(d)} ({d})")

        report.append("\n---- Used Models ----")
        for m in sorted(used_model_files):
            report.append(f"{m} ({all_models.get(m, '')})")

        report.append("\n---- Unused Models ----")
        for m in sorted(unused_models):
            report.append(f"{m} ({all_models.get(m, '')})")

        report.append("\n---- Dependency Summary ----")
        report.append(f"Used Nodes: {len(used_node_types)}")
        report.append(f"Used Models: {len(used_model_files)}")
        report.append(f"Removable Directories: {len(removable_dirs)}")

        print(f"[DEBUG] used_model_files = {used_model_files}")
        print(f"[DEBUG] all_models = {list(all_models.keys())[:20]}")
        
        return ("\n".join(report),)

    # =====================================================
    # Workflow解析
    # =====================================================

    def scan_workflow(self, path, used_node_types, used_model_files, dependency_graph):

        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[DEBUG] Scanning workflow: {path}")
            print(f"[DEBUG] Root JSON type: {type(data)}")

        except Exception as e:
            print(f"[DEBUG] Failed to load JSON: {path}")
            print(f"[DEBUG] Reason: {e}")
            return

        nodes = []

        if isinstance(data, dict):
            if isinstance(data.get("nodes"), dict):
                nodes = data["nodes"].values()
            elif isinstance(data.get("nodes"), list):
                nodes = data["nodes"]
        elif isinstance(data, list):
            nodes = data

        print(f"[DEBUG] Nodes container type: {type(nodes)}")
        
        for node in nodes:
            print(f"[DEBUG] Node keys: {list(node.keys())}")
            print(f"[DEBUG] Node type: {node.get('type')}")
            print(f"[DEBUG] Raw inputs type: {type(node.get('inputs'))}")
            

            node_type = node.get("type")
            if node_type:
                used_node_types.add(node_type)

            raw_inputs = node.get("inputs", {})
            
            # =============================
            # ① inputs 正規化
            # =============================
            if isinstance(raw_inputs, dict):
                inputs = raw_inputs
            
            elif isinstance(raw_inputs, list):
                inputs = {
                    item.get("name"): item.get("value")
                    for item in raw_inputs
                    if isinstance(item, dict) and item.get("name")
                }
            
            else:
                inputs = {}
            
            # =============================
            # ② 🔥 v3 widgets_values 対応をここに追加
            # =============================
            widgets = node.get("widgets_values")
            
            if isinstance(widgets, list):
            
                node_cls = NODE_CLASS_MAPPINGS.get(node_type)
            
                if node_cls:
                    try:
                        input_def = node_cls.INPUT_TYPES()
            
                        ordered_keys = []
            
                        for section in ["required", "optional"]:
                            section_data = input_def.get(section, {})
                            ordered_keys.extend(section_data.keys())
            
                        for key, value in zip(ordered_keys, widgets):
                            if isinstance(value, str):
                                inputs[key] = value
            
                    except Exception as e:
                        print(f"[DEBUG] INPUT_TYPES read failed: {node_type} : {e}")
            

            print(f"[DEBUG] Normalized inputs: {inputs}")

            if node_type not in dependency_graph:
                dependency_graph[node_type] = []

            for value in inputs.values():

                if not isinstance(value, str):
                    continue

                # ① まず拡張子で拾う（Resolver非依存）
                if self.is_model_filename(value):
                    print(f"[DEBUG] Detected model by extension: {value}")
                    filename = os.path.basename(value)
                    used_model_files.add(filename)
                    dependency_graph[node_type].append(filename)

                print(f"[DEBUG] Checking value: {value}")
                # ② Resolverで追加確認
                resolved = self.resolve_model(value)
                if resolved:
                    print(f"[DEBUG] Resolver matched: {resolved}")    
                    filename = os.path.basename(resolved)
                    used_model_files.add(filename)
                    dependency_graph[node_type].append(filename)

                
                for emb in self.extract_embeddings(value):
                    resolved = self.resolve_model(emb)
                    if resolved:
                        filename = os.path.basename(resolved)
                        used_model_files.add(filename)
                        dependency_graph[node_type].append(filename)

    # =====================================================
    # Resolver
    # =====================================================

    def resolve_model(self, value):

        value = value.strip().replace("\\", "/")

        for category in folder_paths.folder_names_and_paths.keys():
            try:
                full_path = folder_paths.get_full_path(category, value)
                if full_path and os.path.exists(full_path):
                    return full_path
            except:
                continue

        return None

    # =====================================================
    # Embedding抽出
    # =====================================================

    def extract_embeddings(self, text):

        results = set()

        matches = re.findall(r"embedding:([\w\-\_\.]+)", text)
        matches += re.findall(r"<embedding:([\w\-\_\.]+)>", text)

        for m in matches:
            if not m.endswith(".pt"):
                m += ".pt"
            results.add(m)

        return results

    # =====================================================
    # モデル全取得
    # =====================================================

    def scan_all_model_files(self):

        all_models = {}

        for category, entry in folder_paths.folder_names_and_paths.items():

            paths = entry[0] if isinstance(entry, tuple) else entry

            if not isinstance(paths, list):
                continue

            for base_path in paths:

                if not os.path.exists(base_path):
                    continue

                for root, _, files in os.walk(base_path):
                    for file in files:
                        if self.is_model_filename(file):
                            full_path = os.path.join(root, file)
                            all_models[file] = full_path

        return all_models

    # =====================================================
    # custom_nodes解析
    # =====================================================

    def get_top_level_custom_nodes(self, custom_nodes_dir):
        return {
            os.path.join(custom_nodes_dir, d)
            for d in os.listdir(custom_nodes_dir)
            if os.path.isdir(os.path.join(custom_nodes_dir, d))
        }

    def build_node_type_path_map(self, custom_nodes_dir):

        mapping = {}

        for node_type, cls in NODE_CLASS_MAPPINGS.items():
            try:
                module = __import__(cls.__module__, fromlist=[""])
                file_path = module.__file__
            except:
                continue

            if file_path and custom_nodes_dir in file_path:
                base_dir = file_path.split(custom_nodes_dir)[-1]
                base_dir = base_dir.strip("\\/").split(os.sep)[0]
                mapping[node_type] = os.path.join(custom_nodes_dir, base_dir)

        return mapping

    def detect_removable_directories(self, top_level_dirs, node_type_to_path, used_node_types):

        # ディレクトリごとに属するnode_typeを集約
        dir_to_node_types = {}

        for node_type, path in node_type_to_path.items():
            dir_to_node_types.setdefault(path, set()).add(node_type)

        removable = set()

        for d in top_level_dirs:

            node_types = dir_to_node_types.get(d, set())

            # node_typeを一つも持たないディレクトリも削除候補
            if not node_types:
                removable.add(d)
                continue

            # すべて未使用なら削除候補
            if all(nt not in used_node_types for nt in node_types):
                removable.add(d)

        return removable

    # =====================================================
    # モデル拡張子判定
    # =====================================================

    def is_model_filename(self, name):

        return isinstance(name, str) and name.lower().endswith((
            ".safetensors",
            ".ckpt",
            ".pt",
            ".pth",
            ".bin",
            ".onnx"
        ))
