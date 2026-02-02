from PIL import Image
import os

def check_dpi(image_path):
    """Check DPI of image and return warning if needed"""
    try:
        with Image.open(image_path) as img:
            # Get DPI from image info
            dpi = img.info.get('dpi', (72, 72))
            
            if dpi[0] < 300 or dpi[1] < 300:
                return "Low Resolution Detected: This file may not print clearly at large sizes."
            
            return None
    except Exception as e:
        print(f"Error checking DPI: {e}")
        return None