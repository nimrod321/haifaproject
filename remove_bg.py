import sys
from PIL import Image
import math

def remove_green(image_path, output_path):
    img = Image.open(image_path).convert("RGBA")
    data = img.getdata()

    new_data = []
    # Base target green
    target_r, target_g, target_b = 0, 255, 0

    for item in data:
        r, g, b, a = item
        # Calculate distance to bright green
        dist = math.sqrt((r - target_r)**2 + (g - target_g)**2 + (b - target_b)**2)
        
        # Also check if it's generally "very green" to catch variations of neon green
        is_green = g > 150 and g > r * 1.5 and g > b * 1.5

        if dist < 120 or is_green:
            new_data.append((255, 255, 255, 0)) # transparent
        else:
            new_data.append(item)

    img.putdata(new_data)
    img.save(output_path, "PNG")

if __name__ == '__main__':
    base_dir = r"C:\Users\נמרוד אלוש\.gemini\antigravity\brain\25e2a87c-f638-4064-b69f-a6bf63a6cec3"
    out_dir = r"C:\Users\Public\Haifa_Project_Updated\client"
    
    files = {
        "chest_open_low_green_v2_1780066700080.png": "chest_open_low.png",
    }

    for in_f, out_f in files.items():
        try:
            print(f"Processing {in_f}...")
            remove_green(f"{base_dir}\\{in_f}", f"{out_dir}\\{out_f}")
        except Exception as e:
            print(f"Error processing {in_f}: {e}")
    print("Done!")
