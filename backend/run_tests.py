import os, sys, pytest

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
project_root = r"C:\Users\avnre\Downloads\diabetes"
backend_dir = os.path.join(project_root, "backend")
scripts_dir = os.path.join(project_root, "scripts")
repo_dir = os.path.join(project_root, "gpformer")
model_v2_gpformer = os.path.join(project_root, "model_v2", "third_party", "gpformer")
model_v2_src = os.path.join(project_root, "model_v2", "src")

for d in [backend_dir, scripts_dir, repo_dir, model_v2_gpformer, model_v2_src]:
    if d not in sys.path:
        sys.path.insert(0, d)

ret = pytest.main([os.path.join(backend_dir, "tests"), "-v", "--tb=short"])
sys.exit(ret)
