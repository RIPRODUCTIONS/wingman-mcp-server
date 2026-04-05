"""
ComfyUI image generation — Flux Schnell model.

Workflow uses the native Flux pipeline with separate model files:
  - UNETLoader:       flux1-schnell.safetensors (diffusion_models/)
  - DualCLIPLoader:   clip_l.safetensors + t5xxl_fp8_e4m3fn.safetensors (text_encoders/)
  - VAELoader:        ae.safetensors (vae/)
  - CLIPTextEncodeFlux → KSampler (4 steps, CFG=1) → VAEDecode → SaveImage

Returns: PNG bytes
"""
import asyncio
import base64
import random
import time
from typing import Any

import httpx

from .. import config


# ---------------------------------------------------------------------------
# API prompt workflow (API format, not UI graph format)
# ---------------------------------------------------------------------------

def _build_workflow(prompt: str, width: int, height: int, steps: int) -> dict[str, Any]:
    """Build ComfyUI API-format workflow for Flux Schnell."""
    seed = random.randint(0, 2**32 - 1)

    return {
        # Node 1: Load VAE
        "1": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": config.FLUX_VAE},
        },
        # Node 2: Load dual CLIP text encoders
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": config.FLUX_CLIP1,
                "clip_name2": config.FLUX_CLIP2,
                "type": "flux",
                "device": "default",
            },
        },
        # Node 3: Empty latent image
        "3": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width":   width,
                "height":  height,
                "batch_size": 1,
            },
        },
        # Node 4: Load diffusion model
        "4": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": config.FLUX_DIFFUSION_MODEL,
                "weight_dtype": "default",
            },
        },
        # Node 5: Text encode (Flux-specific — clip_l + t5 guidance)
        "5": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":     ["2", 0],
                "clip_l":   prompt,
                "t5xxl":    prompt,
                "guidance": 3.5,
            },
        },
        # Node 6: Zero-out negative conditioning (Flux has no negative prompt)
        "6": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["5", 0]},
        },
        # Node 7: KSampler
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model":        ["4", 0],
                "positive":     ["5", 0],
                "negative":     ["6", 0],
                "latent_image": ["3", 0],
                "seed":         seed,
                "steps":        steps,
                "cfg":          1.0,
                "sampler_name": "euler",
                "scheduler":    "simple",
                "denoise":      1.0,
            },
        },
        # Node 8: Decode latent to image
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae":     ["1", 0],
            },
        },
        # Node 9: Save image (returns filename in /tmp output dir)
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images":       ["8", 0],
                "filename_prefix": "x402_mcp",
            },
        },
    }


async def generate_image(
    prompt: str,
    width:  int = 1024,
    height: int = 1024,
    steps:  int = 4,
) -> bytes:
    """
    Submit to ComfyUI, poll until done, return PNG bytes.

    Raises:
        RuntimeError: ComfyUI unreachable or generation failed
    """
    width  = max(64, min(2048, width  - (width  % 8)))
    height = max(64, min(2048, height - (height % 8)))
    steps  = max(1, min(8, steps))

    workflow = _build_workflow(prompt, width, height, steps)

    async with httpx.AsyncClient(base_url=config.COMFYUI_URL, timeout=30.0) as client:
        # 1. Submit prompt
        try:
            resp = await client.post("/prompt", json={"prompt": workflow})
            resp.raise_for_status()
        except httpx.ConnectError:
            raise RuntimeError("ComfyUI is not running at " + config.COMFYUI_URL)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"ComfyUI /prompt error {e.response.status_code}: {e.response.text[:200]}")

        prompt_id = resp.json()["prompt_id"]

        # 2. Poll /history until done (max 120s)
        deadline = time.time() + 120
        output_images: list[dict] = []

        while time.time() < deadline:
            await asyncio.sleep(1.5)
            hist = await client.get(f"/history/{prompt_id}")
            hist.raise_for_status()
            data = hist.json()

            if prompt_id not in data:
                continue  # not done yet

            entry = data[prompt_id]
            if "outputs" not in entry:
                raise RuntimeError("ComfyUI generation failed: no outputs in history")

            for node_out in entry["outputs"].values():
                if "images" in node_out:
                    output_images.extend(node_out["images"])
            break
        else:
            raise RuntimeError("ComfyUI generation timed out after 120s")

        if not output_images:
            raise RuntimeError("ComfyUI returned no images")

        # 3. Fetch the image bytes
        img_meta = output_images[0]
        params = {
            "filename": img_meta["filename"],
            "subfolder": img_meta.get("subfolder", ""),
            "type": img_meta.get("type", "output"),
        }
        img_resp = await client.get("/view", params=params, timeout=30.0)
        img_resp.raise_for_status()
        return img_resp.content
