import os
import json
import folder_paths

MODEL_EXTENSIONS = (
    ".safetensors",
    ".ckpt",
    ".pt",
    ".bin",
    ".pth",
    ".onnx",
    ".gguf",
)

class ComfyUIUsageChecker:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflows_dir": ("STRING", {"default": "user/default/workflows"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "run"
    CATEGORY = "utils"

    # ==========================================
    # Main
    # ==========================================
    def run(self, workflows_dir):

        base = folder_paths.base_path

        if not os.path.isabs(workflows_dir):
            workflows_dir = os.path.join(base, workflows_dir)

        workflows_dir = os.path.normpath(workflows_dir)

        if not os.path.exists(workflows_dir):
            return (f"Workflow dir not found: {workflows_dir}",)

        used_models = set()
        used_node_types = set()

        # 1. Scan workflows
        for root, _, files in os.walk(workflows_dir):
            for file in files:
                if file.endswith(".json"):
                    path = os.path.join(root, file)
                    self.scan_workflow(path, used_models, used_node_types)

        # 2. Scan models
        all_models = self.scan_all_models()

        # 3. Scan custom_nodes
        all_custom_nodes = self.scan_all_custom_nodes()

        # 4. Compare
        # ==========================================
        # Custom Node Matching (改良版)
        # ==========================================
        
        # ---- Models ----
        unused_models = {
            name: path for name, path in all_models.items()
            if name not in used_models
        }
        
        used_models_with_path = {
            name: path for name, path in all_models.items()
            if name in used_models
        }
        
        # ---- Custom Nodes ----
        used_nodes_with_path = {}
        unused_nodes = {}
        
        # 1. workflowで使用されているノードは必ず表示
        for node_type in used_node_types:
            if node_type in all_custom_nodes:
                used_nodes_with_path[node_type] = all_custom_nodes[node_type]
            else:
                # パス不明でも表示
                used_nodes_with_path[node_type] = ""
        
        # 2. custom_nodesフォルダにあるが使われていないもの
        for folder_name, path in all_custom_nodes.items():
            if folder_name not in used_node_types:
                unused_nodes[folder_name] = path

        # 5. Report
        report = []
        report.append("===== ComfyUI Global Usage Report =====\n")
        report.append(f"Scanned Workflows Directory: {workflows_dir}\n")

        report.append("---- Used Models ----")
        for name, path in sorted(used_models_with_path.items()):
            report.append(f"  {name} ({path})")

        report.append("\n---- Unused Models ----")
        for name, path in sorted(unused_models.items()):
            report.append(f"  {name} ({path})")

        report.append("\n---- Used Custom Nodes ----")
        for name, path in sorted(used_nodes_with_path.items()):
            report.append(f"  {name} ({path})")

        report.append("\n---- Unused Custom Nodes ----")
        for name, path in sorted(unused_nodes.items()):
            report.append(f"  {name} ({path})")

        return ("\n".join(report),)

    # ==========================================
    # Workflow Scan (list/dict 両対応)
    # ==========================================
    def scan_workflow(self, path, used_models, used_node_types):

        try:
            with open(path, "r", encoding="utf-8") as f:
                wf = json.load(f)
        except:
            return

        nodes = wf.get("nodes", [])

        if isinstance(nodes, dict):
            iterable = nodes.values()
        elif isinstance(nodes, list):
            iterable = nodes
        else:
            return

        for node in iterable:

            if not isinstance(node, dict):
                continue

            node_type = node.get("type")
            if node_type:
                used_node_types.add(node_type)

            self.extract_models(node, used_models)

    # ==========================================
    # Extract model references
    # ==========================================
    def extract_models(self, obj, used_models):

        if isinstance(obj, dict):
            for v in obj.values():
                self.extract_models(v, used_models)

        elif isinstance(obj, list):
            for item in obj:
                self.extract_models(item, used_models)

        elif isinstance(obj, str):
            lower = obj.lower()
            if any(lower.endswith(ext) for ext in MODEL_EXTENSIONS):
                used_models.add(os.path.basename(obj))

    # ==========================================
    # Scan models recursively
    # ==========================================
    def scan_all_models(self):

        model_root = os.path.join(folder_paths.base_path, "models")
        all_models = {}

        for root, _, files in os.walk(model_root):
            for file in files:
                if file.lower().endswith(MODEL_EXTENSIONS):
                    full_path = os.path.join(root, file)
                    all_models[file] = os.path.normpath(full_path)

        return all_models

    # ==========================================
    # Scan custom_nodes recursively
    # ==========================================
    def scan_all_custom_nodes(self):

        custom_root = os.path.join(folder_paths.base_path, "custom_nodes")
        node_folders = {}

        for root, dirs, files in os.walk(custom_root):
            for d in dirs:
                full = os.path.join(root, d)
                try:
                    if any(f.endswith(".py") for f in os.listdir(full)):
                        node_folders[d] = os.path.normpath(full)
                except:
                    pass

        return node_folders
