import os
import json
import re
import folder_paths
from nodes import NODE_CLASS_MAPPINGS


DEBUG = False  # ← 必要なときだけ True にする


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

        workflow_count = 0

        # =============================
        # Workflow再帰スキャン
        # =============================
        for root, _, files in os.walk(workflow_dir):
            for file in files:
                if not file.endswith(".json"):
                    continue
                if file.startswith("."):
                    continue

                workflow_count += 1

                self.scan_workflow(
                    os.path.join(root, file),
                    used_node_types,
                    used_model_files,
                    dependency_graph
                )

        # =============================
        # custom_nodes解析
        # =============================
        custom_nodes_dir = folder_paths.get_folder_paths("custom_nodes")[0]
        top_level_dirs = self.get_top_level_custom_nodes(custom_nodes_dir)

        node_type_to_path = self.build_node_type_path_map(custom_nodes_dir)

        removable_dirs = self.detect_removable_directories(
            top_level_dirs,
            node_type_to_path,
            used_node_types
        )

        # =============================
        # 全モデル取得
        # =============================
        all_models = self.scan_all_model_files()
        unused_models = set(all_models.keys()) - used_model_files

        if DEBUG:
            print(f"[DEBUG] Scanned workflows: {workflow_count}")
            print(f"[DEBUG] Used nodes: {len(used_node_types)}")
            print(f"[DEBUG] Used models: {len(used_model_files)}")

        # =============================
        # レポート生成
        # =============================
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
        report.append(f"Scanned Workflows: {workflow_count}")
        report.append(f"Used Nodes: {len(used_node_types)}")
        report.append(f"Used Models: {len(used_model_files)}")
        report.append(f"Removable Directories: {len(removable_dirs)}")

        return ("\n".join(report),)

    # =====================================================
    # Workflow解析
    # =====================================================

    def scan_workflow(self, path, used_node_types, used_model_files, dependency_graph):

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        nodes = []

        if isinstance(data, dict):
            if isinstance(data.get("nodes"), dict):
                nodes = data["nodes"].values()
            elif isinstance(data.get("nodes"), list):
                nodes = data["nodes"]
        elif isinstance(data, list):
            nodes = data

        for node in nodes:

            node_type = node.get("type")
            if node_type:
                used_node_types.add(node_type)

            raw_inputs = node.get("inputs", {})

            # inputs正規化
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

            # widgets_values対応
            widgets = node.get("widgets_values")

            if isinstance(widgets, list):
                input_defs = node.get("inputs", [])

                widget_inputs = [
                    inp for inp in input_defs
                    if isinstance(inp, dict) and inp.get("widget") is not None
                ]

                for inp_def, widget_value in zip(widget_inputs, widgets):
                    input_name = inp_def.get("name")
                    if isinstance(widget_value, str):
                        inputs[input_name] = widget_value

            if node_type not in dependency_graph:
                dependency_graph[node_type] = []

            folder_map = self.get_input_folder_map(node_type)

            for key, value in inputs.items():

                if not isinstance(value, str):
                    continue

                filename = os.path.basename(value)

                # folder指定優先
                if key in folder_map:
                    resolved = self.resolve_with_folder(folder_map[key], value)
                    if resolved:
                        fn = os.path.basename(resolved)
                        used_model_files.add(fn)
                        dependency_graph[node_type].append(fn)
                        continue

                # 拡張子検出
                if self.is_model_filename(value):
                    used_model_files.add(filename)
                    dependency_graph[node_type].append(filename)

                # 汎用resolve
                resolved = self.resolve_model(value)
                if resolved:
                    fn = os.path.basename(resolved)
                    used_model_files.add(fn)
                    dependency_graph[node_type].append(fn)

                # embedding検出
                for emb in self.extract_embeddings(value):
                    resolved = self.resolve_model(emb)
                    if resolved:
                        fn = os.path.basename(resolved)
                        used_model_files.add(fn)
                        dependency_graph[node_type].append(fn)

    # =====================================================
    # 以下は変更なし（ロジック維持）
    # =====================================================

    def get_input_folder_map(self, node_type):

        folder_map = {}
        node_cls = NODE_CLASS_MAPPINGS.get(node_type)
        if not node_cls:
            return folder_map

        try:
            input_def = node_cls.INPUT_TYPES()
        except Exception:
            return folder_map

        for section in ["required", "optional"]:
            section_data = input_def.get(section, {})
            for key, config in section_data.items():
                if isinstance(config, tuple) and len(config) > 1:
                    meta = config[1]
                    if isinstance(meta, dict) and "folder" in meta:
                        folder_map[key] = meta["folder"]

        return folder_map

    def resolve_with_folder(self, folder_type, value):
        try:
            full_path = folder_paths.get_full_path(folder_type, value)
            if full_path and os.path.exists(full_path):
                return full_path
        except Exception:
            pass
        return None

    def resolve_model(self, value):
        value = value.strip().replace("\\", "/")
        for category in folder_paths.folder_names_and_paths.keys():
            try:
                full_path = folder_paths.get_full_path(category, value)
                if full_path and os.path.exists(full_path):
                    return full_path
            except Exception:
                continue
        return None

    def extract_embeddings(self, text):
        results = set()
        matches = re.findall(r"embedding:([\w\-\_\.]+)", text)
        matches += re.findall(r"<embedding:([\w\-\_\.]+)>", text)
        for m in matches:
            if not m.endswith(".pt"):
                m += ".pt"
            results.add(m)
        return results

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
            except Exception:
                continue

            if file_path and custom_nodes_dir in file_path:
                base_dir = file_path.split(custom_nodes_dir)[-1]
                base_dir = base_dir.strip("\\/").split(os.sep)[0]
                mapping[node_type] = os.path.join(custom_nodes_dir, base_dir)

        return mapping

    def detect_removable_directories(self, top_level_dirs, node_type_to_path, used_node_types):

        dir_to_node_types = {}

        for node_type, path in node_type_to_path.items():
            dir_to_node_types.setdefault(path, set()).add(node_type)

        removable = set()

        for d in top_level_dirs:
            node_types = dir_to_node_types.get(d, set())
            if not node_types:
                removable.add(d)
                continue
            if all(nt not in used_node_types for nt in node_types):
                removable.add(d)

        return removable

    def is_model_filename(self, name):
        return isinstance(name, str) and name.lower().endswith((
            ".safetensors",
            ".ckpt",
            ".pt",
            ".pth",
            ".bin",
            ".onnx",
            ".gguf"
        ))
