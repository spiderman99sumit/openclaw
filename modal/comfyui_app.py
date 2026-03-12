import modal
import subprocess
import os
import time
import json
import urllib.request

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "wget", "libgl1", "libglib2.0-0")
    .pip_install(
        "numpy<2",
        "torch==2.5.1",
        "torchvision==0.20.1",
        "torchaudio==2.5.1",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .run_commands(
        "git clone https://github.com/comfyanonymous/ComfyUI.git /root/ComfyUI",
        "pip install -r /root/ComfyUI/requirements.txt",
        "mkdir -p /root/ComfyUI/models/checkpoints /root/ComfyUI/models/loras /root/ComfyUI/output"
    )
)

app = modal.App("comfyui-factory", image=image)
vol = modal.Volume.from_name("comfyui-storage", create_if_missing=True)

def wait_for_server():
    for _ in range(90):
        try:
            urllib.request.urlopen("http://127.0.0.1:8188/system_stats")
            return True
        except:
            time.sleep(2)
    return False

@app.function(gpu="A10G", timeout=1200, volumes={"/storage": vol})
def generate_image(prompt: str, negative_prompt: str, job_id: str = "test", image_id: str = "001"):
    ckpt = "/root/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors"
    if not os.path.exists(ckpt):
        subprocess.run([
            "wget",
            "-O",
            ckpt,
            "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
        ], check=True)

    proc = subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
        cwd="/root/ComfyUI",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        if not wait_for_server():
            stderr = ""
            try:
                stderr = proc.stderr.read().decode("utf-8", errors="ignore")[-2000:]
            except:
                pass
            return {"error": "ComfyUI failed to start", "stderr": stderr}

        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1024, "batch_size": 1}
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["4", 1]}
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative_prompt, "clip": ["4", 1]}
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": 30,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]}
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": f"{job_id}_{image_id}", "images": ["8", 0]}
            }
        }

        req = urllib.request.Request(
            "http://127.0.0.1:8188/prompt",
            data=json.dumps({"prompt": workflow}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        prompt_id = json.loads(urllib.request.urlopen(req).read())["prompt_id"]

        for _ in range(180):
            time.sleep(2)
            hist = json.loads(
                urllib.request.urlopen(f"http://127.0.0.1:8188/history/{prompt_id}").read()
            )
            if prompt_id in hist and "9" in hist[prompt_id].get("outputs", {}):
                images = hist[prompt_id]["outputs"]["9"]["images"]
                if images:
                    src = f"/root/ComfyUI/output/{images[0]['filename']}"
                    dst_dir = f"/storage/outputs/{job_id}"
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = f"{dst_dir}/{image_id}.png"
                    subprocess.run(["cp", src, dst], check=True)
                    vol.commit()
                    return {
                        "status": "success",
                        "path": dst,
                        "job_id": job_id,
                        "image_id": image_id
                    }

        return {"error": "generation timeout"}

    finally:
        proc.terminate()
