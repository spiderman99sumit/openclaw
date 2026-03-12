import modal

prompts = [
    {
        "prompt": "Lena Hart, 25-year-old female fitness influencer, feminine athletic build, toned natural physique, healthy glowing skin, soft brown hair in a clean ponytail, confident approachable expression, wearing premium neutral beige activewear set, performing dumbbell walking lunges in a bright modern gym, clean strength aesthetic, full body shot, dynamic forward motion, soft daylight, bright editorial realism, photorealistic",
        "negative_prompt": "lowres, blurry, bad anatomy, extra fingers, extra limbs, deformed hands, watermark, text, logo"
    },
    {
        "prompt": "Lena Hart, 25-year-old female fitness influencer, feminine athletic build, toned natural physique, healthy glowing skin, soft brown hair in a clean ponytail, performing a barbell Romanian deadlift in a clean modern gym, side angle, elegant athletic form, bright open training space, soft daylight, polished commercial Instagram look, photorealistic",
        "negative_prompt": "low quality, lowres, blurry, bad hands, extra limbs, exaggerated muscles, cartoon, anime, watermark, text, logo"
    },
    {
        "prompt": "Lena Hart, 25-year-old female fitness influencer, feminine athletic build, healthy glowing skin, soft brown hair tied back neatly, seated cable row in a bright modern gym, three-quarter angle, strong back posture, clean strength coach vibe, premium fitness creator, photorealistic",
        "negative_prompt": "blurry, lowres, bad anatomy, extra arms, distorted hands, dark moody gym, cartoon, anime, watermark, text, logo"
    }
]

fn = modal.Function.from_name("comfyui-factory", "generate_image")

results = []
for i, p in enumerate(prompts, start=1):
    print(f"Generating image {i}/{len(prompts)} ...")
    res = fn.remote(
        prompt=p["prompt"],
        negative_prompt=p["negative_prompt"],
        job_id="JOB-20260312-001",
        image_id=f"{i:03d}"
    )
    print(res)
    results.append(res)

print("\nDone.")
print(results)
