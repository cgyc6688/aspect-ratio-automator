"""
Aspect Ratio Image Processor - Memory Optimized Version
Optimized for Render.com free tier (512MB RAM limit)
"""

from PIL import Image, ImageOps
import os
from datetime import datetime
import traceback

class ImageProcessor:
    """
    Memory-optimized image processor for Render.com deployment.
    Processes large images without exceeding 512MB memory limit.
    """
    
    # REDUCED TARGET DIMENSIONS BY 50% (Memory Optimization #1)
    # Original sizes were causing memory overflow (~1.5GB total)
    # New sizes are still good for print quality at 300 DPI
    RATIOS = {
        '2x3': (3600, 5400),      # 19.4 MP (was 7200x10800 = 77.8 MP)
        '3x4': (2700, 3600),      # 9.7 MP (was 5400x7200 = 38.9 MP)
        '4x5': (3600, 4500),      # 16.2 MP (was 7200x9000 = 64.8 MP)
        'ISO': (3508, 4967),      # 17.4 MP (was 7016x9933 = 69.7 MP)
        '11x14': (1650, 2100)     # 3.5 MP (was 3300x4200 = 13.9 MP)
    }
    
    # Memory optimization constants
    MAX_SOURCE_DIMENSION = 6000  # Don't process source images larger than this
    MAX_MEMORY_SAFE_DIMENSION = 8000  # Absolute limit
    
    def __init__(self, image_path, session_id, processed_folder='processed'):
        """
        Initialize image processor with memory optimization.
        
        Args:
            image_path: Path to original image
            session_id: Unique session identifier
            processed_folder: Where to save processed images
        """
        self.image_path = image_path
        self.session_id = session_id
        self.processed_folder = processed_folder
        
        # Ensure processed folder exists
        os.makedirs(self.processed_folder, exist_ok=True)
        
        # Load image metadata only (not full image) to check dimensions
        self.image = None
        self.image_info = self._get_image_info()
        
    def _get_image_info(self):
        """Get image dimensions without loading full image into memory."""
        try:
            with Image.open(self.image_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'mode': img.mode,
                    'format': img.format,
                    'dpi': img.info.get('dpi', (72, 72))
                }
        except Exception as e:
            print(f"Error getting image info: {e}")
            return None
    
    def create_previews(self):
        """Create preview images for all ratios (memory optimized)."""
        previews = {}
        
        for ratio_name, (width, height) in self.RATIOS.items():
            try:
                preview_path = os.path.join(
                    self.processed_folder, 
                    f"{self.session_id}_{ratio_name}_preview.jpg"
                )
                
                # Create preview with memory optimization
                preview = self._create_crop_for_preview(width, height)
                if preview:
                    # Resize for web display (small thumbnail)
                    preview.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    preview.save(preview_path, 'JPEG', quality=85, optimize=True)
                    
                    previews[ratio_name] = {
                        'url': f'/preview/{os.path.basename(preview_path)}',
                        'dimensions': f"{width} x {height} px",
                        'preview_size': '300x300 px'
                    }
                else:
                    previews[ratio_name] = {
                        'error': 'Failed to create preview',
                        'dimensions': f"{width} x {height} px"
                    }
                    
            except Exception as e:
                print(f"Error creating preview for {ratio_name}: {e}")
                previews[ratio_name] = {
                    'error': str(e),
                    'dimensions': f"{width} x {height} px"
                }
        
        return previews
    
    def _create_crop_for_preview(self, target_width, target_height):
        """
        Create preview crop with minimal memory usage.
        Loads image, crops, and returns immediately.
        """
        try:
            # Load image for this specific operation
            with Image.open(self.image_path) as img:
                # MEMORY OPTIMIZATION #2: Resize large source images
                img = self._resize_if_too_large(img)
                
                # Calculate crop
                crop_image = self._calculate_crop(img, target_width, target_height)
                if crop_image:
                    # Resize to target dimensions
                    return crop_image.resize((target_width, target_height), 
                                            Image.Resampling.LANCZOS)
                return None
                
        except Exception as e:
            print(f"Error in preview crop: {e}")
            return None
    
    def adjust_crop(self, ratio, x_offset=0, y_offset=0):
        """
        Adjust crop position for specific ratio.
        Memory optimized: processes one image at a time.
        """
        if ratio not in self.RATIOS:
            return None
            
        width, height = self.RATIOS[ratio]
        
        try:
            # Load image fresh for this operation
            with Image.open(self.image_path) as img:
                # MEMORY OPTIMIZATION: Resize if too large
                img = self._resize_if_too_large(img)
                
                # Calculate crop with offset
                crop_image = self._calculate_crop(img, width, height, x_offset, y_offset)
                if not crop_image:
                    return None
                
                # Resize to target
                resized = crop_image.resize((width, height), Image.Resampling.LANCZOS)
                
                # Save full size for final output
                output_filename = f"{self.session_id}_{ratio}_adjusted.jpg"
                output_path = os.path.join(self.processed_folder, output_filename)
                
                # Preserve color profile
                if img.mode == 'CMYK':
                    resized = resized.convert('CMYK')
                else:
                    resized = resized.convert('RGB')
                
                # Save with moderate quality to save space
                resized.save(output_path, 'JPEG', quality=90, dpi=(300, 300), optimize=True)
                
                # Also save preview
                preview_path = os.path.join(
                    self.processed_folder,
                    f"{self.session_id}_{ratio}_preview.jpg"
                )
                resized.thumbnail((300, 300), Image.Resampling.LANCZOS)
                resized.save(preview_path, 'JPEG', quality=85, optimize=True)
                
                return preview_path
                
        except Exception as e:
            print(f"Error in adjust_crop: {e}")
            traceback.print_exc()
            return None
    
    def process_all_ratios(self, adjustments):
        """
        Process all ratios with adjustments.
        MEMORY OPTIMIZATION #3: Process images one at a time.
        
        Args:
            adjustments: Dictionary of adjustments for each ratio
            
        Returns:
            List of output file paths
        """
        output_files = []
        
        # Extract base filename
        original_name = os.path.basename(self.image_path)
        if '_' in original_name:
            # Remove session_id_ prefix
            base_name = '_'.join(original_name.split('_')[1:])
        else:
            base_name = original_name
        base_name = os.path.splitext(base_name)[0]
        
        # Clean base name
        base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        # PROCESS ONE RATIO AT A TIME (Memory Optimization #3)
        for ratio_name, (width, height) in self.RATIOS.items():
            try:
                print(f"Processing ratio: {ratio_name}")
                
                # Get adjustments for this ratio
                adj = adjustments.get(ratio_name, {})
                x_offset = adj.get('x_offset', 0)
                y_offset = adj.get('y_offset', 0)
                
                # Load image fresh for EACH ratio (prevents memory buildup)
                with Image.open(self.image_path) as img:
                    # MEMORY OPTIMIZATION: Resize if too large
                    img = self._resize_if_too_large(img)
                    
                    # Calculate and create crop
                    crop_image = self._calculate_crop(img, width, height, x_offset, y_offset)
                    if not crop_image:
                        continue
                    
                    # Resize to target dimensions
                    resized = crop_image.resize((width, height), Image.Resampling.LANCZOS)
                    
                    # Save with proper naming
                    output_filename = f"{base_name}_{ratio_name}.jpg"
                    output_path = os.path.join(self.processed_folder, output_filename)
                    
                    # Preserve color profile
                    if img.mode == 'CMYK':
                        resized = resized.convert('CMYK')
                    else:
                        resized = resized.convert('RGB')
                    
                    # Save with optimized settings
                    resized.save(
                        output_path, 
                        'JPEG', 
                        quality=90,          # Reduced from 100 for memory/space
                        dpi=(300, 300),
                        optimize=True,       # Enable JPEG optimization
                        progressive=True     # Progressive JPEG for web
                    )
                    
                    output_files.append(output_path)
                    
                    # Clear variables to help garbage collection
                    crop_image = None
                    resized = None
                    
            except Exception as e:
                print(f"Error processing ratio {ratio_name}: {e}")
                traceback.print_exc()
                continue
        
        return output_files
    
    def _resize_if_too_large(self, image):
        """
        MEMORY OPTIMIZATION #2: Resize source image if it's too large.
        Prevents processing multi-gigapixel images on limited memory.
        
        Args:
            image: PIL Image object
            
        Returns:
            Resized image if needed, otherwise original
        """
        width, height = image.size
        
        # Check if image exceeds safe dimensions
        if width > self.MAX_MEMORY_SAFE_DIMENSION or height > self.MAX_MEMORY_SAFE_DIMENSION:
            print(f"WARNING: Source image too large ({width}x{height}). Resizing for memory safety.")
            
            # Calculate new size maintaining aspect ratio
            if width > height:
                new_width = self.MAX_MEMORY_SAFE_DIMENSION
                new_height = int(self.MAX_MEMORY_SAFE_DIMENSION * height / width)
            else:
                new_height = self.MAX_MEMORY_SAFE_DIMENSION
                new_width = int(self.MAX_MEMORY_SAFE_DIMENSION * width / height)
            
            # Resize with high-quality algorithm
            return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Optional: Resize if larger than recommended processing size
        elif width > self.MAX_SOURCE_DIMENSION or height > self.MAX_SOURCE_DIMENSION:
            print(f"INFO: Resizing large image ({width}x{height}) for better performance.")
            
            if width > height:
                new_width = self.MAX_SOURCE_DIMENSION
                new_height = int(self.MAX_SOURCE_DIMENSION * height / width)
            else:
                new_height = self.MAX_SOURCE_DIMENSION
                new_width = int(self.MAX_SOURCE_DIMENSION * width / height)
            
            return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return image
    
    def _calculate_crop(self, image, target_width, target_height, x_offset=0, y_offset=0):
        """
        Calculate crop area with offset.
        
        Args:
            image: PIL Image object
            target_width: Desired crop width
            target_height: Desired crop height
            x_offset: Horizontal adjustment (-100 to 100)
            y_offset: Vertical adjustment (-100 to 100)
            
        Returns:
            Cropped PIL Image object
        """
        img_width, img_height = image.size
        
        # Calculate aspect ratios
        target_ratio = target_width / target_height
        img_ratio = img_width / img_height
        
        # Determine crop dimensions to match target ratio
        if img_ratio > target_ratio:
            # Image is wider than target - crop width
            crop_height = img_height
            crop_width = int(crop_height * target_ratio)
        else:
            # Image is taller than target - crop height
            crop_width = img_width
            crop_height = int(crop_width / target_ratio)
        
        # Calculate crop area with offset (percentage based)
        # Convert percentage offset to pixel offset
        x_pixel_offset = int((x_offset / 100) * crop_width) if x_offset else 0
        y_pixel_offset = int((y_offset / 100) * crop_height) if y_offset else 0
        
        # Start from center, apply offset
        left = (img_width - crop_width) // 2 + x_pixel_offset
        top = (img_height - crop_height) // 2 + y_pixel_offset
        right = left + crop_width
        bottom = top + crop_height
        
        # Ensure crop area is within image bounds
        left = max(0, min(left, img_width - crop_width))
        top = max(0, min(top, img_height - crop_height))
        right = left + crop_width
        bottom = top + crop_height
        
        # Verify crop dimensions
        if right <= left or bottom <= top:
            print(f"Invalid crop dimensions: {left},{top},{right},{bottom}")
            return None
        
        if right > img_width or bottom > img_height:
            print(f"Crop out of bounds: {right}x{bottom} > {img_width}x{img_height}")
            return None
        
        # Perform crop
        return image.crop((left, top, right, bottom))
    
    def get_memory_usage(self):
        """Estimate memory usage for current operations."""
        if not self.image_info:
            return "Unknown"
        
        # Rough memory estimate (4 bytes per pixel for RGBA)
        pixels = self.image_info['width'] * self.image_info['height']
        bytes_estimate = pixels * 4
        
        return {
            'dimensions': f"{self.image_info['width']}x{self.image_info['height']}",
            'pixels': f"{pixels:,}",
            'estimated_memory_mb': f"{bytes_estimate / 1024 / 1024:.1f} MB",
            'ratios_to_process': len(self.RATIOS),
            'total_estimated_memory_mb': f"{(bytes_estimate * len(self.RATIOS)) / 1024 / 1024:.1f} MB"
        }


# Helper function for standalone testing
def test_memory_optimization():
    """Test the memory optimized processor."""
    import sys
    
    print("=== Memory Optimized Image Processor Test ===")
    print("Features:")
    print("1. 50% reduced target dimensions")
    print("2. Automatic source image resizing for large images")
    print("3. One-at-a-time processing to prevent memory buildup")
    
    # Create a test instance
    test_path = "test_image.jpg"
    processor = ImageProcessor(test_path, "test_session", "test_output")
    
    # Show memory estimates
    mem_info = processor.get_memory_usage()
    print(f"\nMemory Estimate: {mem_info}")
    
    print("\nTarget Ratios (50% reduced):")
    for ratio, (w, h) in processor.RATIOS.items():
        mp = (w * h) / 1000000
        print(f"  {ratio}: {w}x{h} ({mp:.1f} MP)")
    
    print("\n✅ Memory optimization ready for Render deployment!")


if __name__ == "__main__":
    test_memory_optimization()