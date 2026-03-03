"""
Generate Dummy Images for Testing
Run this script to create placeholder images for device testing
"""

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL not available. Install with: pip install Pillow")

import os

def generate_dummy_image(device_id, patient_name, output_path):
    """Generate a simple placeholder image for a device"""
    
    if not PIL_AVAILABLE:
        print(f"Cannot generate image for {device_id} - PIL not installed")
        return False
    
    # Create image
    width, height = 640, 480
    image = Image.new('RGB', (width, height), color=(45, 45, 68))
    draw = ImageDraw.Draw(image)
    
    # Try to use a font, fall back to default if not available
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Draw text
    text1 = f"Device: {device_id}"
    text2 = f"Patient: {patient_name}"
    text3 = "Captured Image"
    
    # Center text
    bbox1 = draw.textbbox((0, 0), text1, font=font_large)
    bbox2 = draw.textbbox((0, 0), text2, font=font_small)
    bbox3 = draw.textbbox((0, 0), text3, font=font_small)
    
    x1 = (width - (bbox1[2] - bbox1[0])) // 2
    x2 = (width - (bbox2[2] - bbox2[0])) // 2
    x3 = (width - (bbox3[2] - bbox3[0])) // 2
    
    draw.text((x1, 150), text1, fill=(78, 205, 196), font=font_large)
    draw.text((x2, 220), text2, fill=(255, 255, 255), font=font_small)
    draw.text((x3, 280), text3, fill=(160, 160, 160), font=font_small)
    
    # Draw camera icon shape
    draw.rectangle([(270, 320), (370, 380)], outline=(78, 205, 196), width=3)
    draw.ellipse([(295, 335), (345, 385)], outline=(78, 205, 196), width=2)
    
    # Save
    image.save(output_path, 'JPEG', quality=85)
    print(f"Generated: {output_path}")
    return True

if __name__ == '__main__':
    # Device data from dummy_data.py
    devices = [
        ('device_001', 'Margaret Smith'),
        ('device_002', 'John Anderson'),
        ('device_004', 'Robert Chen')
    ]
    
    output_dir = 'static/images/captured'
    os.makedirs(output_dir, exist_ok=True)
    
    success_count = 0
    for device_id, patient_name in devices:
        filename = f'{device_id}_latest.jpg'
        filepath = os.path.join(output_dir, filename)
        if generate_dummy_image(device_id, patient_name, filepath):
            success_count += 1
    
    print(f"\n[SUCCESS] Generated {success_count}/{len(devices)} images")
    
    if not PIL_AVAILABLE:
        print("\nNote: To generate images, install Pillow:")
        print("   pip install Pillow")
        print("   Then run this script again: python generate_dummy_images.py")
