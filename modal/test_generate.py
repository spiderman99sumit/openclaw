import modal

# First prompt from JOB-20260312-001
prompt = "Lena Hart, 25-year-old female fitness influencer, feminine athletic build, toned natural physique, healthy glowing skin, soft brown hair in a clean ponytail, confident approachable expression, wearing premium neutral beige activewear set, performing dumbbell walking lunges in a bright modern gym, clean strength aesthetic, full body shot, soft daylight, bright editorial realism, SDXL, ultra detailed, photorealistic, 8k"

negative = "lowres, blurry, bad anatomy, extra fingers, extra limbs, deformed hands, cartoon, anime, CGI, watermark, text, logo"

generate = modal.Function.from_name("comfyui-factory", "generate_image")

print("Generating test image...")
result = generate.remote(
    prompt=prompt,
    negative_prompt=negative,
    seed=42,
    steps=30,
    cfg=7.0,
    width=1024,
    height=1024,
    job_id="JOB-20260312-001",
    image_id="test-001",
)
print(f"Result: {result}")
