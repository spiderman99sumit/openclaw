import modal
import subprocess
import os
import time
import json
import urllib.request

comfyui_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "wget", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.1.2",
        "torchvision==0.16.2",
        "torchaudio==2.1.2",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install("comfy-cli", "aiohttp", "requests", "Pillow", "numpy", "safetensors")
    .run_commands("comfy install --skip-prompt --nvidia")
    .run_commands(
        "comfy model download --url https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors --relative-path models/checkpoints/"
    )
)

app = modal.App("comfyui-factory", image=comfyui_image)
vol = modal.Volume.from_name("comfyui-storage", create_if_missing=True)


def wait_for_server(url="http://127.0.0.1:8188", timeout=60):
    for i in range(timeout // 2):
        try:
            urllib.request.urlopen(f"{url}/system_stats")
            return True
        except:
            time.sleep(2)
    return False


def start_comfyui():
    proc = subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
        cwd="/root/comfy/ComfyUI",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not wait_for_server():
        raise RuntimeError("ComfyUI failed to start")
    return proc


def build_workflow(prompt, negative_prompt, seed, steps, cfg, width, height,
                   lora_name=None, lora_weight=0.8, filename_prefix="output"):
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative_prompt, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed if seed >= 0 else int(time.time()),
                         "steps": steps, "cfg": cfg,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "denoise": 1.0, "model": ["4", 0],
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}},
    }
    if lora_name:
        wf["10"] = {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": lora_name,
                       "strength_model": lora_weight, "strength_clip": lora_weight,
                       "model": ["4", 0], "clip": ["4", 1]},
        }
        wf["3"]["inputs"]["model"] = ["10", 0]
        wf["6"]["inputs"]["clip"] = ["10", 1]
        wf["7"]["inputs"]["clip"] = ["10", 1]
    return wf


@app.function(gpu="A10G", timeout=600, volumes={"/storage": vol})
def generate_image(prompt: str, negative_prompt: str, seed: int = -1,
                   steps: int = 30, cfg: float = 7.0,
                   width: int = 1024, height: int = 1024,
                   lora_name: str = None, lora_weight: float = 0.8,
                   job_id: str = "test", image_id: str = "001"):
    proc = start_comfyui()
    try:
        prefix = f"{job_id}_{image_id}"
        wf = build_workflow(prompt, negative_prompt, seed, steps, cfg,
                            width, height, lora_name, lora_weight, prefix)
        data = json.dumps({"prompt": wf}).encode()
        req = urllib.request.Request("http://127.0.0.1:8188/prompt",
                                     data=data,
                                     headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req).read())
        pid = resp["prompt_id"]

        for _ in range(120):
            time.sleep(2)
            hist = json.loads(
                urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}").read()
            )
            if pid in hist and "9" in hist[pid].get("outputs", {}):
                images = hist[pid]["outputs"]["9"]["images"]
                if images:
                    src = f"/root/comfy/ComfyUI/output/{images[0]['filename']}"
                    dst_dir = f"/storage/outputs/{job_id}"
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = f"{dst_dir}/{image_id}.png"
                    subprocess.run(["cp", src, dst])
                    vol.commit()
                    return {"status": "success", "job_id": job_id,
                            "image_id": image_id, "path": dst,
                            "size": os.path.getsize(dst),
                            "seed": wf["3"]["inputs"]["seed"]}
        return {"error": "timeout"}
    finally:
        proc.terminate()


@app.function(gpu="A10G", timeout=3600, volumes={"/storage": vol})
def generate_batch(prompts: list, job_id: str = "test",
                   lora_name: str = None, lora_weight: float = 0.8):
    proc = start_comfyui()
    results = []
    try:
        for i, p in enumerate(prompts):
            prefix = f"{job_id}_{i+1:03d}"
            wf = build_workflow(
                p["prompt"], p["negative_prompt"],
                p.get("seed", -1), p.get("steps", 30), p.get("cfg", 7.0),
                p.get("width", 1024), p.get("height", 1024),
                lora_name, lora_weight, prefix,
            )
            data = json.dumps({"prompt": wf}).encode()
            req = urllib.request.Request("http://127.0.0.1:8188/prompt",
                                         data=data,
                                         headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req).read())
            pid = resp["prompt_id"]

            success = False
            for _ in range(120):
                time.sleep(2)
                hist = json.loads(
                    urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}").read()
                )
                if pid in hist and "9" in hist[pid].get("outputs", {}):
                    images = hist[pid]["outputs"]["9"]["images"]
                    if images:
                        src = f"/root/comfy/ComfyUI/output/{images[0]['filename']}"
                        dst_dir = f"/storage/outputs/{job_id}"
                        os.makedirs(dst_dir, exist_ok=True)
                        dst = f"{dst_dir}/{i+1:03d}.png"
                        subprocess.run(["cp", src, dst])
                        results.append({"status": "success", "image": f"{i+1:03d}.png"})
                        print(f"  ✅ Image {i+1}/{len(prompts)}")
                        success = True
                        break
            if not success:
                results.append({"status": "timeout", "image": f"{i+1:03d}.png"})
                print(f"  ❌ Image {i+1}/{len(prompts)} timed out")
        vol.commit()
    finally:
        proc.terminate()
    return results
