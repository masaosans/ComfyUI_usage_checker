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
                "workflows_dir": ("STRING", {"default": "workflows"}),
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

        workflows_dir = os.path.abspath(workflows_dir)

        if not os.path.exists(workflows_dir):
            return (f"Workflow dir not found: {workflows_dir}",)

        used_models = set()
        used_node_types = set()

        # 1. Scan all workflows
        for root, _, files in os.walk(workflows_dir):
            for file in files:
                if file.endswith(".json"):
                    path = os.path.join(root, file)
                    self.scan_workflow(path, used_models, used_node_types)

        # 2. Scan models directory recursively
        all_models = self.scan_all_models()

        # 3. Scan custom_nodes recursively
        all_custom_nodes = self.scan_all_custom_nodes()

        # 4. Compare
        unused_models = all_models - used_models
        unused_nodes = all_custom_nodes - used_node_types

        # 5. Build report
        report = []
        report.append("===== ComfyUI Global Usage Report =====\n")

        report.append(f"Scanned Workflows Directory: {workflows_dir}\n")

        report.append("---- Used Models ----")
        for m in sorted(used_models):
            report.append(f"  {m}")

        report.append("\n---- Unused Models ----")
        for m in sorted(unused_models):
            report.append(f"  {m}")

        report.append("\n---- Used Node Types ----")
        for n in sorted(used_node_types):
            report.append(f"  {n}")

        report.append("\n---- Unused Custom Node Folders ----")
        for n in sorted(unused_nodes):
            report.append(f"  {n}")

        return ("\n".join(report),)

    # ==========================================
    # Scan workflow JSON
    # ==========================================
    def scan_workflow(self, path, used_models, used_node_types):

        try:
            with open(path, "r", encoding="utf-8") as f:
                wf = json.load(f)
        except:
            return

        nodes = wf.get("nodes", {})

        for _, node in nodes.items():

            node_type = node.get("type")
            if node_type:
                used_node_types.add(node_type)

            self.extract_models(node, used_models)

    # ==========================================
    # Recursively extract model references
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
    # Recursively scan models directory
    # ==========================================
    def scan_all_models(self):

        model_root = os.path.join(folder_paths.base_path, "models")
        all_models = set()

        for root, _, files in os.walk(model_root):
            for file in files:
                if file.lower().endswith(MODEL_EXTENSIONS):
                    all_models.add(file)

        return all_models

    # ==========================================
    # Recursively scan custom_nodes directory
    # ==========================================
    def scan_all_custom_nodes(self):

        custom_root = os.path.join(folder_paths.base_path, "custom_nodes")
        node_folders = set()

        for root, dirs, files in os.walk(custom_root):
            for d in dirs:
                full = os.path.join(root, d)
                try:
                    if any(f.endswith(".py") for f in os.listdir(full)):
                        node_folders.add(d)
                except:
                    pass

        return node_folders
