from PIL import Image, ImageOps
import os
from datetime import datetime

class ImageProcessor:
    RATIOS = {
        '2x3': (7200, 10800),
        '3x4': (5400, 7200),
        '4x5': (7200, 9000),
        'ISO': (7016, 9933),
        '11x14': (3300, 4200)
    }
    
    def __init__(self, image_path, session_id, processed_folder='processed'):
        self.image_path = image_path
        self.session_id = session_id
        self.processed_folder = processed_folder  # NEW: Accept folder as parameter
        self.image = Image.open(image_path)
        # Ensure processed folder exists
        os.makedirs(self.processed_folder, exist_ok=True)
        
    def create_previews(self):
        """Create preview images for all ratios"""
        previews = {}
        
        for ratio_name, (width, height) in self.RATIOS.items():
            preview_path = os.path.join(
                self.processed_folder, 
                f"{self.session_id}_{ratio_name}_preview.jpg"
            )
            
            # Create preview (scaled down for web display)
            preview = self._create_crop(self.image, width, height)
            preview.thumbnail((300, 300))  # Resize for preview
            preview.save(preview_path, 'JPEG', quality=85)
            
            previews[ratio_name] = {
                'url': f'/preview/{self.session_id}/{ratio_name}',
                'dimensions': f"{width} x {height} px"
            }
        
        return previews
    
    def adjust_crop(self, ratio, x_offset=0, y_offset=0):
        """Adjust crop position for specific ratio"""
        width, height = self.RATIOS[ratio]
        
        # Calculate crop with offset
        crop_image = self._create_crop(self.image, width, height, x_offset, y_offset)
        
        # Save full size for final output
        output_path = os.path.join(
            self.processed_folder,
            f"{self.session_id}_{ratio}_adjusted.jpg"
        )
        crop_image.save(output_path, 'JPEG', quality=95, dpi=(300, 300))
        
        # Also save preview
        preview_path = os.path.join(
            self.processed_folder,
            f"{self.session_id}_{ratio}_preview.jpg"
        )
        crop_image.thumbnail((300, 300))
        crop_image.save(preview_path, 'JPEG', quality=85)
        
        return preview_path
    
    def process_all_ratios(self, adjustments):
        """Process all ratios with adjustments and return file paths"""
        output_files = []
        original_name = os.path.basename(self.image_path).split('_', 1)[-1]
        base_name = os.path.splitext(original_name)[0]
        
        for ratio_name, (width, height) in self.RATIOS.items():
            # Get adjustments for this ratio
            adj = adjustments.get(ratio_name, {})
            x_offset = adj.get('x_offset', 0)
            y_offset = adj.get('y_offset', 0)
            
            # Create crop
            crop_image = self._create_crop(self.image, width, height, x_offset, y_offset)
            
            # Save with proper naming
            output_filename = f"{base_name}_{ratio_name}.jpg"
            output_path = os.path.join(self.processed_folder, output_filename)
            
            # Preserve color profile
            if self.image.mode == 'CMYK':
                crop_image = crop_image.convert('CMYK')
            else:
                crop_image = crop_image.convert('RGB')
            
            crop_image.save(
                output_path, 
                'JPEG', 
                quality=100,
                dpi=(300, 300),
                optimize=True
            )
            
            output_files.append(output_path)
        
        return output_files
    
    def _create_crop(self, image, target_width, target_height, x_offset=0, y_offset=0):
        """Create crop with optional offset"""
        img_width, img_height = image.size
        
        # Calculate aspect ratios
        target_ratio = target_width / target_height
        img_ratio = img_width / img_height
        
        if img_ratio > target_ratio:
            # Image is wider than target
            new_height = img_height
            new_width = int(new_height * target_ratio)
        else:
            # Image is taller than target
            new_width = img_width
            new_height = int(new_width / target_ratio)
        
        # Calculate crop area with offset
        left = (img_width - new_width) // 2 + x_offset
        top = (img_height - new_height) // 2 + y_offset
        right = left + new_width
        bottom = top + new_height
        
        # Ensure crop area is within image bounds
        left = max(0, min(left, img_width - new_width))
        top = max(0, min(top, img_height - new_height))
        right = left + new_width
        bottom = top + new_height
        
        # Crop and resize
        cropped = image.crop((left, top, right, bottom))
        resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        return resized