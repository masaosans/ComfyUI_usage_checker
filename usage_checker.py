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

        for root, _, files in os.walk(workflow_dir):
            for file in files:
                if file.endswith(".json"):
                    self.scan_workflow(
                        os.path.join(root, file),
                        used_node_types,
                        used_model_files,
                        dependency_graph
                    )

        custom_nodes_dir = folder_paths.get_folder_paths("custom_nodes")[0]
        all_custom_nodes = self.scan_custom_nodes(custom_nodes_dir)

        all_models = self.scan_all_model_files()

        node_type_to_path = self.build_node_type_path_map(custom_nodes_dir)

        used_node_paths = set(
            node_type_to_path.get(nt)
            for nt in used_node_types
            if nt in node_type_to_path
        )

        unused_nodes = all_custom_nodes - used_node_paths
        unused_models = set(all_models.keys()) - used_model_files

        report = []
        report.append("===== USAGE REPORT =====\n")

        report.append("---- Used Custom Nodes ----")
        for nt in sorted(used_node_types):
            path = node_type_to_path.get(nt, "")
            report.append(f"{nt} ({path})")

        report.append("\n---- Unused Custom Nodes ----")
        for path in sorted(unused_nodes):
            report.append(f"{os.path.basename(path)} ({path})")

        report.append("\n---- Used Models ----")
        for m in sorted(used_model_files):
            report.append(f"{m} ({all_models.get(m, '')})")

        report.append("\n---- Unused Models ----")
        for m in sorted(unused_models):
            report.append(f"{m} ({all_models.get(m, '')})")

        report.append("\n---- Dependency Summary ----")
        report.append(f"Used Nodes: {len(used_node_types)}")
        report.append(f"Used Models: {len(used_model_files)}")

        return ("\n".join(report),)

    # =====================================================
    # Workflow解析
    # =====================================================

    def scan_workflow(self, path, used_node_types, used_model_files, dependency_graph):
    
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            return
    
        nodes = []
    
        if isinstance(data, dict):
            if isinstance(data.get("nodes"), dict):
                nodes = data["nodes"].values()
            elif isinstance(data.get("nodes"), list):
                nodes = data["nodes"]
        elif isinstance(data, list):
            nodes = data
    
        model_input_map = self.build_dynamic_model_input_map()
    
        for node in nodes:
    
            node_type = node.get("type")
            if not node_type:
                continue
    
            used_node_types.add(node_type)
    
            raw_inputs = node.get("inputs", {})
    
            # inputs 正規化
            if isinstance(raw_inputs, dict):
                inputs = raw_inputs
    
            elif isinstance(raw_inputs, list):
                inputs = {}
                for item in raw_inputs:
                    if isinstance(item, dict):
                        name = item.get("name")
                        value = item.get("value")
                        if name:
                            inputs[name] = value
            else:
                inputs = {}
    
            if node_type not in dependency_graph:
                dependency_graph[node_type] = []
    
            # 動的モデル検出
            if node_type in model_input_map:
                for key in model_input_map[node_type]:
                    val = inputs.get(key)
                    if isinstance(val, str):
                        used_model_files.add(val)
                        dependency_graph[node_type].append(val)
    
            # Embedding検出
            for v in inputs.values():
                if isinstance(v, str):
                    embeddings = self.extract_embeddings(v)
                    for emb in embeddings:
                        used_model_files.add(emb)
                        dependency_graph[node_type].append(emb)
    
            # フォールバック拡張子検出
            for v in inputs.values():
                if isinstance(v, str) and self.is_model_filename(v):
                    used_model_files.add(v)
                    dependency_graph[node_type].append(v)


    # =====================================================
    # Embedding抽出
    # =====================================================

    def extract_embeddings(self, text):

        results = set()

        # embedding:xxx
        matches = re.findall(r"embedding:([\w\-\_\.]+)", text)
        for m in matches:
            if not m.endswith(".pt"):
                m += ".pt"
            results.add(m)

        # <embedding:xxx>
        matches = re.findall(r"<embedding:([\w\-\_\.]+)>", text)
        for m in matches:
            if not m.endswith(".pt"):
                m += ".pt"
            results.add(m)

        return results

    # =====================================================
    # 動的INPUT_TYPES解析
    # =====================================================

    def build_dynamic_model_input_map(self):

        model_input_map = {}

        for node_type, cls in NODE_CLASS_MAPPINGS.items():

            try:
                input_types = cls.INPUT_TYPES()
            except:
                continue

            detected = []

            for section in ["required", "optional"]:
                section_data = input_types.get(section, {})

                for input_name, input_def in section_data.items():

                    if not isinstance(input_def, tuple):
                        continue

                    input_type = input_def[0]
                    options = input_def[1] if len(input_def) > 1 else {}

                    if isinstance(options, dict) and "folder" in options:
                        detected.append(input_name)
                        continue

                    if input_type in [
                        "MODEL",
                        "CLIP",
                        "VAE",
                        "CONTROL_NET",
                        "CONDITIONING"
                    ]:
                        detected.append(input_name)
                        continue

                    lowered = input_name.lower()
                    keywords = [
                        "ckpt", "model", "lora", "vae",
                        "control", "clip", "unet",
                        "encoder", "embedding"
                    ]

                    if any(k in lowered for k in keywords):
                        detected.append(input_name)

            if detected:
                model_input_map[node_type] = detected

        return model_input_map

    # =====================================================
    # モデル全取得
    # =====================================================

    def scan_all_model_files(self):
    
        all_models = {}
    
        for category, entry in folder_paths.folder_names_and_paths.items():
    
            # ComfyUIバージョン差異対応
            if isinstance(entry, tuple):
                paths = entry[0]  # (paths, options)
            else:
                paths = entry
    
            if not isinstance(paths, list):
                continue
    
            for base_path in paths:
    
                if not isinstance(base_path, (str, bytes, os.PathLike)):
                    continue
    
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

    def scan_custom_nodes(self, path):
        result = set()
        for root, dirs, _ in os.walk(path):
            for d in dirs:
                result.add(os.path.join(root, d))
        return result

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

    # =====================================================
    # モデル拡張子判定
    # =====================================================

    def is_model_filename(self, name):

        if not isinstance(name, str):
            return False

        return name.lower().endswith((
            ".safetensors",
            ".ckpt",
            ".pt",
            ".pth",
            ".bin",
            ".onnx"
        ))
