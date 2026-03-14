"""
Modal ComfyUI Face Swap Deployment
GPU: L40S
API: POST /swap (face_image + body_image as base64 → result image)

Setup:
 1. modal secret create civitai-token CIVITAI_TOKEN=your_token
 2. modal secret create huggingface-secret HF_TOKEN=hf_your_token
 3. modal run scripts/modal_faceswap.py # download models once
 4. modal deploy scripts/modal_faceswap.py # deploy app
"""

import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import modal

app = modal.App("comfyui-faceswap")

volume = modal.Volume.from_name("comfyui-faceswap-models", create_if_missing=True)
VOLUME_PATH = "/mnt/faceswap-volume"
MODELS_BASE = f"{VOLUME_PATH}/ComfyUI/models"
COMFYUI_PATH = "/root/comfy/ComfyUI"
COMFYUI_PORT = 8188

CIVITAI_TOKEN = os.environ.get("CIVITAI_TOKEN", "")

# ─── Docker image ───

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "wget", "curl", "libgl1", "libglib2.0-0", "libglib2.0-dev")
    .pip_install(
        "torch==2.4.1",
        "torchvision==0.19.1",
        "torchaudio==2.4.1",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "comfy-cli",
        "huggingface_hub[hf_transfer]",
        "hf_transfer",
        "httpx",
        "fastapi",
        "uvicorn",
        "Pillow",
        "pyyaml",
        "setuptools<82",  # Required for ComfyUI_LayerStyle_Advance
        "insightface",
        "onnxruntime-gpu",
    )
    .run_commands(
        "comfy --skip-prompt install --nvidia --cuda-version 12.4",
    )
    .run_commands(
        f"git clone https://github.com/kijai/ComfyUI-KJNodes {COMFYUI_PATH}/custom_nodes/ComfyUI-KJNodes",
        f"cd {COMFYUI_PATH}/custom_nodes/ComfyUI-KJNodes && pip install -r requirements.txt || true",
        f"git clone https://github.com/chflame163/ComfyUI_LayerStyle_Advance {COMFYUI_PATH}/custom_nodes/ComfyUI_LayerStyle_Advance",
        f"cd {COMFYUI_PATH}/custom_nodes/ComfyUI_LayerStyle_Advance && pip install -r requirements.txt || true",
        f"git clone https://github.com/cubiq/ComfyUI_FaceAnalysis {COMFYUI_PATH}/custom_nodes/ComfyUI_FaceAnalysis",
        f"cd {COMFYUI_PATH}/custom_nodes/ComfyUI_FaceAnalysis && pip install -r requirements.txt || true",
        f"git clone https://github.com/BadCafeCode/masquerade-nodes-comfyui {COMFYUI_PATH}/custom_nodes/masquerade-nodes-comfyui",
        f"git clone https://github.com/Ryuukeisyou/comfyui_face_parsing {COMFYUI_PATH}/custom_nodes/comfyui_face_parsing",
        f"cd {COMFYUI_PATH}/custom_nodes/comfyui_face_parsing && pip install -r requirements.txt || true",
                # ComfyUI_Swwan (provides ImageResize+, ImageConcanate, etc)
        f"git clone https://github.com/aining2022/ComfyUI_Swwan {COMFYUI_PATH}/custom_nodes/ComfyUI_Swwan && "
        f"cd {COMFYUI_PATH}/custom_nodes/ComfyUI_Swwan && pip install -r requirements.txt || true && "
        f"echo 'Swwan installed:' && ls {COMFYUI_PATH}/custom_nodes/ComfyUI_Swwan/*.py 2>/dev/null | head -20",
        # Backup: efficiency-nodes also provides ImageResize+
        f"git clone https://github.com/jags111/efficiency-nodes-comfyui {COMFYUI_PATH}/custom_nodes/efficiency-nodes-comfyui || true",
        f"cd {COMFYUI_PATH}/custom_nodes/efficiency-nodes-comfyui && pip install -r requirements.txt 2>/dev/null || true",
        f"git clone https://github.com/a-und-b/ComfyUI_LoRA_from_URL {COMFYUI_PATH}/custom_nodes/ComfyUI_LoRA_from_URL",
    )
    .run_commands("pip install 'setuptools<82'")
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "COMFYUI_PATH": COMFYUI_PATH,
    })
)


# ─── Model download helpers ───

def hf_url_file(url, dest_path):
    dest = Path(dest_path)
    if dest.exists():
        return f"exists: {dest.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "-L", "--retry", "3", "-o", str(dest), url],
        check=True,
        capture_output=True,
    )
    return f"downloaded: {dest.name}"


def curl_file(url, dest_path):
    dest = Path(dest_path)
    if dest.exists():
        return f"exists: {dest.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "-L", "--retry", "3", "-o", str(dest), url],
        check=True,
        capture_output=True,
    )
    return f"downloaded: {dest.name}"


def download_all_models(civitai_token=""):
    unet_dir = f"{MODELS_BASE}/unet"
    diffusion_models_dir = f"{MODELS_BASE}/diffusion_models"
    text_encoders_dir = f"{MODELS_BASE}/clip"
    vae_dir = f"{MODELS_BASE}/vae"

    token = civitai_token or CIVITAI_TOKEN

    tasks = [
        (
            curl_file,
            (
                f"https://civitai.com/api/download/models/2740209?type=Model&format=SafeTensor&size=pruned&fp=fp8&token={token}",
                f"{unet_dir}/darkBeastMar0326Latest_dbkleinv2BFS.safetensors",
            ),
        ),
        (
            hf_url_file,
            (
                "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-9b/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors?download=true",
                f"{text_encoders_dir}/qwen_3_8b_fp8mixed.safetensors",
            ),
        ),
        (
            hf_url_file,
            (
                "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-9b/resolve/main/split_files/vae/flux2-vae.safetensors?download=true",
                f"{vae_dir}/flux2-vae.safetensors",
            ),
        ),
        (
            hf_url_file,
            (
                "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors?download=true",
                f"{diffusion_models_dir}/z_image_turbo_bf16.safetensors",
            ),
        ),
        (
            hf_url_file,
            (
                "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors?download=true",
                f"{text_encoders_dir}/qwen_3_4b.safetensors",
            ),
        ),
        (
            hf_url_file,
            (
                "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors?download=true",
                f"{vae_dir}/ae.safetensors",
            ),
        ),
    ]

    print(f"Downloading {len(tasks)} model files...\n")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn, *args): args for fn, args in tasks}
        for fut in as_completed(futures):
            try:
                print(fut.result())
            except Exception as e:
                print(f"Error: {e}")

    volume.commit()
    print("\nAll models ready!")


# ─── Symlink models ───

def setup_model_paths():
    dst = Path(f"{COMFYUI_PATH}/models")
    src = Path(MODELS_BASE)
    src.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        dst.unlink()
    if dst.exists():
        import shutil
        shutil.rmtree(dst)
    dst.symlink_to(src)


# ─── Start ComfyUI ───

_comfyui_proc = None


def start_comfyui():
    global _comfyui_proc
    if _comfyui_proc and _comfyui_proc.poll() is None:
        return

    setup_model_paths()

    cmd = [
        "python",
        f"{COMFYUI_PATH}/main.py",
        "--listen",
        "0.0.0.0",
        "--port",
        str(COMFYUI_PORT),
        "--disable-auto-launch",
        "--preview-method",
        "none",
        "--enable-cors-header",
        "*",
    ]
    _comfyui_proc = subprocess.Popen(cmd)

    print("Waiting for ComfyUI...")
    for _ in range(120):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{COMFYUI_PORT}/system_stats", timeout=3
            )
            print("ComfyUI ready!")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("ComfyUI did not start")


# ─── Upload image to ComfyUI ───

def upload_image_to_comfyui(image_bytes: bytes, filename: str) -> str:
    """Upload an image to ComfyUI's input directory and return the filename."""
    input_dir = Path(f"{COMFYUI_PATH}/input")
    input_dir.mkdir(parents=True, exist_ok=True)
    filepath = input_dir / filename
    filepath.write_bytes(image_bytes)
    return filename


# ─── Build workflow ───

def build_faceswap_workflow(face_filename: str, body_filename: str, seed: int) -> dict:
    """Build the face swap workflow with injected face and body images."""
    return {
        "28": {
            "inputs": {
                "face": True,
                "hair": False,
                "body": False,
                "clothes": False,
                "accessories": False,
                "background": False,
                "confidence": 0.2,
                "detail_method": "VITMatte(local)",
                "detail_erode": 6,
                "detail_dilate": 6,
                "black_point": 0.01,
                "white_point": 0.99,
                "process_detail": True,
                "device": "cuda",
                "max_megapixels": 2,
                "images": ["295", 0],
            },
            "class_type": "LayerMask: PersonMaskUltra V2",
            "_meta": {"title": "LayerMask: PersonMaskUltra V2(Advance)"},
        },
        "37": {
            "inputs": {"pixels": ["295", 0], "vae": ["293", 0]},
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode"},
        },
        "38": {
            "inputs": {"samples": ["37", 0], "mask": ["28", 1]},
            "class_type": "SetLatentNoiseMask",
            "_meta": {"title": "Set Latent Noise Mask"},
        },
        "58": {
            "inputs": {"model": ["59", 0], "processor": ["60", 0], "image": ["245", 0]},
            "class_type": "FaceParse(FaceParsing)",
            "_meta": {"title": "FaceParse(FaceParsing)"},
        },
        "59": {
            "inputs": {"device": "cuda"},
            "class_type": "FaceParsingModelLoader(FaceParsing)",
            "_meta": {"title": "FaceParsingModelLoader(FaceParsing)"},
        },
        "60": {
            "inputs": {},
            "class_type": "FaceParsingProcessorLoader(FaceParsing)",
            "_meta": {"title": "FaceParsingProcessorLoader(FaceParsing)"},
        },
        "62": {
            "inputs": {
                "background": False,
                "skin": False,
                "nose": True,
                "eye_g": False,
                "r_eye": True,
                "l_eye": True,
                "r_brow": True,
                "l_brow": True,
                "r_ear": False,
                "l_ear": False,
                "mouth": True,
                "u_lip": True,
                "l_lip": True,
                "hair": False,
                "hat": False,
                "ear_r": False,
                "neck_l": False,
                "neck": False,
                "cloth": False,
                "result": ["58", 1],
            },
            "class_type": "FaceParsingResultsParser(FaceParsing)",
            "_meta": {"title": "FaceParsingResultsParser(FaceParsing)"},
        },
        "66": {
            "inputs": {
                "expand": 10,
                "incremental_expandrate": 0,
                "tapered_corners": True,
                "flip_input": False,
                "blur_radius": 5,
                "lerp_alpha": 1,
                "decay_factor": 1,
                "fill_holes": False,
                "mask": ["62", 0],
            },
            "class_type": "GrowMaskWithBlur",
            "_meta": {"title": "Grow Mask With Blur"},
        },
        "82": {
            "inputs": {
                "force_resize_width": 0,
                "force_resize_height": 0,
                "image": ["245", 0],
                "mask": ["84", 0],
            },
            "class_type": "Cut By Mask",
            "_meta": {"title": "Cut By Mask"},
        },
        "84": {
            "inputs": {"mask": ["66", 0]},
            "class_type": "MaskToImage",
            "_meta": {"title": "Convert Mask to Image"},
        },
        "86": {
            "inputs": {
                "x": 0,
                "y": 0,
                "resize_source": False,
                "destination": ["245", 0],
                "source": ["251", 0],
                "mask": ["66", 0],
            },
            "class_type": "ImageCompositeMasked",
            "_meta": {"title": "ImageCompositeMasked"},
        },
        "242": {
            "inputs": {
                "padding": 300,
                "padding_percent": 0,
                "index": 0,
                "analysis_models": ["247", 0],
                "image": ["296", 0],
            },
            "class_type": "FaceBoundingBox",
            "_meta": {"title": "Face Bounding Box"},
        },
        "245": {
            "inputs": {
                "width": 1000,
                "height": 1000,
                "interpolation": "lanczos",
                "method": "keep proportion",
                "condition": "always",
                "multiple_of": 0,
                "image": ["242", 0],
            },
            "class_type": "ImageResize+",
            "_meta": {"title": "Image Resize"},
        },
        "247": {
            "inputs": {"library": "insightface", "provider": "CUDA"},
            "class_type": "FaceAnalysisModels",
            "_meta": {"title": "Face Analysis Models"},
        },
        "250": {
            "inputs": {
                "padding": 300,
                "padding_percent": 0,
                "index": 0,
                "analysis_models": ["253", 0],
                "image": ["295", 0],
            },
            "class_type": "FaceBoundingBox",
            "_meta": {"title": "Face Bounding Box"},
        },
        "251": {
            "inputs": {
                "width": 1000,
                "height": 1000,
                "interpolation": "lanczos",
                "method": "keep proportion",
                "condition": "always",
                "multiple_of": 0,
                "image": ["250", 0],
            },
            "class_type": "ImageResize+",
            "_meta": {"title": "Image Resize"},
        },
        "253": {
            "inputs": {"library": "insightface", "provider": "CUDA"},
            "class_type": "FaceAnalysisModels",
            "_meta": {"title": "Face Analysis Models"},
        },
        "255": {
            "inputs": {
                "width": ["242", 3],
                "height": ["242", 4],
                "interpolation": "lanczos",
                "method": "keep proportion",
                "condition": "always",
                "multiple_of": 0,
                "image": ["86", 0],
            },
            "class_type": "ImageResize+",
            "_meta": {"title": "Image Resize"},
        },
        "256": {
            "inputs": {
                "x": ["242", 1],
                "y": ["242", 2],
                "resize_source": False,
                "destination": ["296", 0],
                "source": ["255", 0],
                "mask": ["66", 0],
            },
            "class_type": "ImageCompositeMasked",
            "_meta": {"title": "ImageCompositeMasked"},
        },
        "259": {
            "inputs": {"filename_prefix": "faceswap_out", "images": ["256", 0]},
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
        },
        "271": {
            "inputs": {
                "text": "bad quality, noise, blurry, worst quality, low resolution, blur, distortion, unnatural blending, cartoon, illustration, painting",
                "clip": ["304", 0],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Negative Prompt)"},
        },
        "272": {
            "inputs": {"sampler_name": "lcm"},
            "class_type": "KSamplerSelect",
            "_meta": {"title": "KSamplerSelect"},
        },
        "273": {
            "inputs": {
                "cfg": 1,
                "model": ["279", 0],
                "positive": ["286", 0],
                "negative": ["283", 0],
            },
            "class_type": "CFGGuider",
            "_meta": {"title": "CFGGuider"},
        },
        "274": {
            "inputs": {"noise_seed": seed},
            "class_type": "RandomNoise",
            "_meta": {"title": "RandomNoise"},
        },
        "275": {
            "inputs": {"conditioning": ["271", 0], "latent": ["276", 0]},
            "class_type": "ReferenceLatent",
            "_meta": {"title": "ReferenceLatent"},
        },
        "276": {
            "inputs": {"pixels": ["298", 0], "vae": ["305", 0]},
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode"},
        },
        "277": {
            "inputs": {
                "aspect_ratio": "original",
                "proportional_width": 1,
                "proportional_height": 1,
                "fit": "letterbox",
                "method": "lanczos",
                "round_to_multiple": "8",
                "scale_to_side": "longest",
                "scale_to_length": 1280,
                "background_color": "#000000",
                "image": ["306", 0],
            },
            "class_type": "LayerUtility: ImageScaleByAspectRatio V2",
            "_meta": {"title": "LayerUtility: ImageScaleByAspectRatio V2"},
        },
        "278": {
            "inputs": {"conditioning": ["288", 0], "latent": ["276", 0]},
            "class_type": "ReferenceLatent",
            "_meta": {"title": "ReferenceLatent"},
        },
        "279": {
            "inputs": {"strength": 1, "model": ["303", 0]},
            "class_type": "DifferentialDiffusion",
            "_meta": {"title": "Differential Diffusion"},
        },
        "280": {
            "inputs": {"image": ["298", 0]},
            "class_type": "GetImageSize",
            "_meta": {"title": "Get Image Size"},
        },
        "281": {
            "inputs": {"width": ["280", 0], "height": ["280", 1], "batch_size": 1},
            "class_type": "EmptyFlux2LatentImage",
            "_meta": {"title": "Empty Flux 2 Latent"},
        },
        "282": {
            "inputs": {
                "noise": ["274", 0],
                "guider": ["273", 0],
                "sampler": ["272", 0],
                "sigmas": ["289", 0],
                "latent_image": ["281", 0],
            },
            "class_type": "SamplerCustomAdvanced",
            "_meta": {"title": "SamplerCustomAdvanced"},
        },
        "283": {
            "inputs": {"conditioning": ["275", 0], "latent": ["284", 0]},
            "class_type": "ReferenceLatent",
            "_meta": {"title": "ReferenceLatent"},
        },
        "284": {
            "inputs": {"pixels": ["277", 0], "vae": ["305", 0]},
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode"},
        },
        "285": {
            "inputs": {
                "direction": "right",
                "match_image_size": True,
                "image1": ["287", 0],
                "image2": ["295", 0],
            },
            "class_type": "ImageConcanate",
            "_meta": {"title": "Image Concatenate (Swwan)"},
        },
        "286": {
            "inputs": {"conditioning": ["278", 0], "latent": ["284", 0]},
            "class_type": "ReferenceLatent",
            "_meta": {"title": "ReferenceLatent"},
        },
        "287": {
            "inputs": {
                "direction": "down",
                "match_image_size": True,
                "image1": ["298", 0],
                "image2": ["277", 0],
            },
            "class_type": "ImageConcanate",
            "_meta": {"title": "Image Concatenate (Swwan)"},
        },
        "288": {
            "inputs": {
                "text": (
                    "head_swap: Picture 1 is the base image. Keep the body,\n"
                    "neck, clothing, background, lighting, and pose exactly\n"
                    "from Picture 1. Take ONLY the face shape, hair, eye\n"
                    "color, skin texture, and bone structure from Picture 2.\n"
                    "Ignore Picture 2's expression entirely.\n\n"
                    "The person has a very subtle, barely noticeable soft\n"
                    "smile. Mouth is fully closed, lips gently pressed\n"
                    "together, corners of the lips only very slightly\n"
                    "curved upward. No teeth visible at all. Zero teeth\n"
                    "showing. Lips are relaxed and natural. Eyes are calm\n"
                    "and relaxed with a soft gentle warmth, looking\n"
                    "directly at camera. Eyebrows are completely relaxed\n"
                    "and neutral, not raised. Cheeks are naturally resting,\n"
                    "not pushed up. Jaw is relaxed and unclenched. Face\n"
                    "muscles are calm and unstrained.\n\n"
                    "The expression is quiet, understated, minimal,\n"
                    "restrained — like a person who is content but\n"
                    "not reacting to anything.\n\n"
                    "AVOID: laughing, grinning, smiling wide, open mouth,\n"
                    "teeth showing, any teeth visible, exaggerated smile,\n"
                    "big smile, broad smile, raised cheeks, squinting,\n"
                    "crow's feet, dimples, any sign of laughter, excited\n"
                    "expression, joyful expression, enthusiastic expression.\n\n"
                    "Seamless blend at the neck, matched skin tone and\n"
                    "lighting, photorealistic, 4k, sharp details."
                ),
                "clip": ["304", 0],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Positive Prompt)"},
        },
        "289": {
            "inputs": {"steps": 6, "width": ["280", 0], "height": ["280", 1]},
            "class_type": "Flux2Scheduler",
            "_meta": {"title": "Flux2Scheduler"},
        },
        "290": {
            "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"},
            "class_type": "CLIPLoader",
            "_meta": {"title": "Load CLIP"},
        },
        "291": {
            "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"},
            "class_type": "UNETLoader",
            "_meta": {"title": "Load Diffusion Model"},
        },
        "292": {
            "inputs": {
                "text": "waxy skin, airbrushed skin, smooth skin, bad hands, worst quality, low quality, bad anatomy, low detail:1.4",
                "clip": ["290", 0],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Negative Prompt)"},
        },
        "293": {
            "inputs": {"vae_name": "ae.safetensors"},
            "class_type": "VAELoader",
            "_meta": {"title": "Load VAE"},
        },
        "295": {
            "inputs": {"samples": ["282", 0], "vae": ["305", 0]},
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
        },
        "296": {
            "inputs": {"samples": ["297", 0], "vae": ["293", 0]},
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
        },
        "297": {
            "inputs": {
                "seed": seed + 1,
                "steps": 5,
                "cfg": 1,
                "sampler_name": "euler",
                "scheduler": "ddim_uniform",
                "denoise": 0.3,
                "model": ["291", 0],
                "positive": ["299", 0],
                "negative": ["292", 0],
                "latent_image": ["38", 0],
            },
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
        },
        "298": {
            "inputs": {
                "aspect_ratio": "original",
                "proportional_width": 1,
                "proportional_height": 1,
                "fit": "letterbox",
                "method": "lanczos",
                "round_to_multiple": "8",
                "scale_to_side": "longest",
                "scale_to_length": 1536,
                "background_color": "#000000",
                "image": ["307", 0],
            },
            "class_type": "LayerUtility: ImageScaleByAspectRatio V2",
            "_meta": {"title": "LayerUtility: ImageScaleByAspectRatio V2"},
        },
        "299": {
            "inputs": {
                "text": "A high-resolution realistic photograph of an adult woman",
                "clip": ["290", 0],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Z-image CLIP Text Encode (Positive Prompt)"},
        },
        "303": {
            "inputs": {
                "unet_name": "darkBeastMar0326Latest_dbkleinv2BFS.safetensors",
                "weight_dtype": "default",
            },
            "class_type": "UNETLoader",
            "_meta": {"title": "Load Diffusion Model"},
        },
        "304": {
            "inputs": {
                "clip_name": "qwen_3_8b_fp8mixed.safetensors",
                "type": "flux2",
                "device": "default",
            },
            "class_type": "CLIPLoader",
            "_meta": {"title": "Load CLIP"},
        },
        "305": {
            "inputs": {"vae_name": "flux2-vae.safetensors"},
            "class_type": "VAELoader",
            "_meta": {"title": "Load VAE"},
        },
        "306": {
            "inputs": {"image": face_filename},
            "class_type": "LoadImage",
            "_meta": {"title": "face"},
        },
        "307": {
            "inputs": {"image": body_filename},
            "class_type": "LoadImage",
            "_meta": {"title": "body"},
        },
    }


# ─── Queue and wait ───

def queue_and_wait(workflow: dict, client_id: str) -> list:
    import httpx

    base = f"http://127.0.0.1:{COMFYUI_PORT}"

    r = httpx.post(
        f"{base}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    print(f"Queued: {prompt_id}")

    outputs = None
    for attempt in range(300):
        time.sleep(2)
        hist = httpx.get(f"{base}/history/{prompt_id}", timeout=10).json()
        if prompt_id in hist:
            outputs = hist[prompt_id].get("outputs", {})
            break
        if attempt % 15 == 0:
            print(f"Processing... ({attempt * 2}s)")
    else:
        raise TimeoutError("Generation timed out")

    images = []
    for node_output in outputs.values():
        for img_info in node_output.get("images", []):
            params = urllib.parse.urlencode(
                {
                    "filename": img_info["filename"],
                    "subfolder": img_info.get("subfolder", ""),
                    "type": img_info["type"],
                }
            )
            img_bytes = httpx.get(f"{base}/view?{params}", timeout=60).content
            images.append(img_bytes)

    print(f"Got {len(images)} image(s)")
    return images


# ─── Modal Functions ───

@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    timeout=3600,
    secrets=[
        modal.Secret.from_name("huggingface-secret"),
        modal.Secret.from_name("civitai-token"),
    ],
)
def download_models_to_volume():
    civitai_token = os.environ.get("CIVITAI_TOKEN", "")
    download_all_models(civitai_token=civitai_token)


@app.function(
    image=image,
    gpu="L40S",
    volumes={VOLUME_PATH: volume},
    scaledown_window=60,
    timeout=600,
    secrets=[
        modal.Secret.from_name("huggingface-secret"),
        modal.Secret.from_name("civitai-token"),
    ],
)
@modal.fastapi_endpoint(method="POST", docs=True)
async def swap(request: dict):
    """
    Face swap endpoint.
    Accepts JSON body with base64-encoded face and body images.
    Returns the face-swapped result as PNG.

    Body: {"face_image": "<base64>", "body_image": "<base64>", "seed": 42}
    """
    import random
    from fastapi.responses import JSONResponse, Response

    face_image = request.get("face_image", "")
    body_image = request.get("body_image", "")
    seed = request.get("seed", -1)

    if not face_image or not body_image:
        return JSONResponse(
            status_code=400,
            content={"error": "Both face_image and body_image (base64) are required"},
        )

    start_comfyui()

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    face_bytes = base64.b64decode(face_image)
    body_bytes = base64.b64decode(body_image)

    face_fn = f"face_{uuid.uuid4().hex[:8]}.png"
    body_fn = f"body_{uuid.uuid4().hex[:8]}.png"

    upload_image_to_comfyui(face_bytes, face_fn)
    upload_image_to_comfyui(body_bytes, body_fn)

    print(f"Swapping: seed={seed}")

    workflow = build_faceswap_workflow(face_fn, body_fn, seed)
    images = queue_and_wait(workflow, str(uuid.uuid4()))

    if not images:
        return JSONResponse(status_code=500, content={"error": "No output"})

    return Response(content=images[0], media_type="image/png")


@app.local_entrypoint()
def main():
    print("Downloading models to Modal Volume...")
    download_models_to_volume.remote()
    print("\nDone! Now run:")
    print("modal deploy scripts/modal_faceswap.py")
