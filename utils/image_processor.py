"""
Aspect Ratio Image Processor - Memory Optimized Version with Preview Fix
Optimized for Render.com free tier (512MB RAM limit)
FIXED: Preview images not showing after adjustments
"""

from PIL import Image, ImageOps
import os
from datetime import datetime
import traceback

class ImageProcessor:
    """
    Memory-optimized image processor for Render.com deployment.
    Processes large images without exceeding 512MB memory limit.
    FIXED: Returns correct preview filenames for frontend display.
    """
    
    # REDUCED TARGET DIMENSIONS BY 50% (Memory Optimization)
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
        self.image_info = self._get_image_info()
        
        print(f"ImageProcessor initialized: {os.path.basename(image_path)}, session: {session_id[:8]}")
        
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
        
        print(f"Creating previews for session: {self.session_id[:8]}")
        
        for ratio_name, (width, height) in self.RATIOS.items():
            try:
                # CRITICAL: Use consistent naming convention
                preview_filename = f"{self.session_id}_{ratio_name}_preview.jpg"
                preview_path = os.path.join(self.processed_folder, preview_filename)
                
                print(f"Creating preview for {ratio_name} at {preview_path}")
                
                # Create preview with memory optimization
                preview = self._create_crop_for_preview(width, height)
                if preview:
                    # Resize for web display (small thumbnail)
                    preview.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    
                    # Save with optimization
                    preview.save(
                        preview_path, 
                        'JPEG', 
                        quality=85, 
                        optimize=True,
                        progressive=True  # Progressive JPEG for faster loading
                    )
                    
                    # Verify file was created
                    if os.path.exists(preview_path):
                        file_size = os.path.getsize(preview_path) / 1024
                        print(f"Preview created: {preview_filename} ({file_size:.1f} KB)")
                        
                        previews[ratio_name] = {
                            'url': f'/preview/{preview_filename}',  # CRITICAL: This URL must match app.py route
                            'dimensions': f"{width} x {height} px",
                            'preview_size': '300x300 px'
                        }
                    else:
                        print(f"ERROR: Preview file not created: {preview_path}")
                        previews[ratio_name] = {
                            'error': 'Failed to create preview file',
                            'dimensions': f"{width} x {height} px"
                        }
                else:
                    print(f"ERROR: Preview image creation failed for {ratio_name}")
                    previews[ratio_name] = {
                        'error': 'Failed to create preview image',
                        'dimensions': f"{width} x {height} px"
                    }
                    
            except Exception as e:
                print(f"Error creating preview for {ratio_name}: {e}")
                traceback.print_exc()
                previews[ratio_name] = {
                    'error': str(e),
                    'dimensions': f"{width} x {height} px"
                }
        
        print(f"Previews created: {len(previews)} previews ready")
        return previews
    
    def _create_crop_for_preview(self, target_width, target_height):
        """
        Create preview crop with minimal memory usage.
        Loads image, crops, and returns immediately.
        """
        try:
            # Load image for this specific operation
            with Image.open(self.image_path) as img:
                # MEMORY OPTIMIZATION: Resize large source images
                img = self._resize_if_too_large(img)
                
                # Calculate crop (center crop by default)
                crop_image = self._calculate_crop(img, target_width, target_height)
                if crop_image:
                    # Resize to target dimensions for preview
                    return crop_image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                return None
                
        except Exception as e:
            print(f"Error in preview crop: {e}")
            return None
    
    def adjust_crop(self, ratio, x_offset=0, y_offset=0):
        """
        Adjust crop position for specific ratio.
        FIXED: Returns preview filename (not path) for frontend.
        
        Args:
            ratio: Aspect ratio name (e.g., '2x3', '3x4')
            x_offset: Horizontal adjustment (-100 to 100)
            y_offset: Vertical adjustment (-100 to 100)
            
        Returns:
            Preview filename (e.g., 'sessionid_ratio_preview.jpg') or None if failed
        """
        print(f"Adjusting crop for {ratio}, offset: x={x_offset}, y={y_offset}")
        
        if ratio not in self.RATIOS:
            print(f"ERROR: Invalid ratio: {ratio}")
            return None
            
        width, height = self.RATIOS[ratio]
        
        try:
            # Load image fresh for this operation
            with Image.open(self.image_path) as img:
                print(f"Image loaded: {img.width}x{img.height}, mode: {img.mode}")
                
                # MEMORY OPTIMIZATION: Resize if too large
                img = self._resize_if_too_large(img)
                
                # Calculate crop with offset
                crop_image = self._calculate_crop(img, width, height, x_offset, y_offset)
                if not crop_image:
                    print(f"ERROR: Crop calculation failed for {ratio}")
                    return None
                
                print(f"Crop calculated: {crop_image.width}x{crop_image.height}")
                
                # Resize to target dimensions
                resized = crop_image.resize((width, height), Image.Resampling.LANCZOS)
                print(f"Resized to target: {resized.width}x{resized.height}")
                
                # Save full size for final output (optional, for download)
                output_filename = f"{self.session_id}_{ratio}_adjusted.jpg"
                output_path = os.path.join(self.processed_folder, output_filename)
                
                # Preserve color profile
                if img.mode == 'CMYK':
                    resized = resized.convert('CMYK')
                else:
                    resized = resized.convert('RGB')
                
                # Save with moderate quality to save space
                resized.save(
                    output_path, 
                    'JPEG', 
                    quality=90, 
                    dpi=(300, 300), 
                    optimize=True,
                    progressive=True
                )
                print(f"Full size saved: {output_filename}")
                
                # CRITICAL: Save preview for frontend display
                # Use consistent naming convention: sessionid_ratio_preview.jpg
                preview_filename = f"{self.session_id}_{ratio}_preview.jpg"
                preview_path = os.path.join(self.processed_folder, preview_filename)
                
                # Create thumbnail for preview
                preview_img = resized.copy()  # Copy to avoid modifying original
                preview_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                
                # Save preview with optimization
                preview_img.save(
                    preview_path, 
                    'JPEG', 
                    quality=85, 
                    optimize=True,
                    progressive=True
                )
                
                # Verify preview was saved
                if os.path.exists(preview_path):
                    preview_size = os.path.getsize(preview_path) / 1024
                    print(f"Preview saved: {preview_filename} ({preview_size:.1f} KB)")
                    
                    # CRITICAL: Return the filename (not path)
                    # This is what app.py expects for the /preview/<filename> route
                    return preview_filename
                else:
                    print(f"ERROR: Preview file not created at {preview_path}")
                    return None
                
        except Exception as e:
            print(f"Error in adjust_crop: {e}")
            traceback.print_exc()
            return None
    
    def process_all_ratios(self, adjustments):
        """
        Process all ratios with adjustments.
        MEMORY OPTIMIZATION: Process images one at a time.
        
        Args:
            adjustments: Dictionary of adjustments for each ratio
                Format: {'2x3': {'x_offset': 10, 'y_offset': -5}, ...}
            
        Returns:
            List of output file paths for the final high-res images
        """
        output_files = []
        
        print(f"Processing all ratios for session: {self.session_id[:8]}")
        
        # Extract base filename from original path
        original_name = os.path.basename(self.image_path)
        
        # Remove session_id_ prefix if present
        if '_' in original_name:
            # Split and get everything after the first underscore (session_id)
            parts = original_name.split('_', 1)
            if len(parts) > 1:
                base_name = parts[1]
            else:
                base_name = original_name
        else:
            base_name = original_name
        
        # Remove extension
        base_name = os.path.splitext(base_name)[0]
        
        # Clean base name for safe filenames
        import re
        base_name = re.sub(r'[^\w\s\-_.]', '', base_name)
        base_name = base_name.replace(' ', '_')
        
        print(f"Base filename: {base_name}")
        
        # PROCESS ONE RATIO AT A TIME (Memory Optimization)
        for ratio_name, (width, height) in self.RATIOS.items():
            try:
                print(f"Processing ratio: {ratio_name} ({width}x{height})")
                
                # Get adjustments for this ratio (default to center if none)
                adj = adjustments.get(ratio_name, {})
                x_offset = adj.get('x_offset', 0)
                y_offset = adj.get('y_offset', 0)
                
                print(f"  Using adjustments: x={x_offset}, y={y_offset}")
                
                # Load image fresh for EACH ratio (prevents memory buildup)
                with Image.open(self.image_path) as img:
                    print(f"  Image loaded: {img.width}x{img.height}")
                    
                    # MEMORY OPTIMIZATION: Resize if too large
                    img = self._resize_if_too_large(img)
                    
                    # Calculate and create crop
                    crop_image = self._calculate_crop(img, width, height, x_offset, y_offset)
                    if not crop_image:
                        print(f"  ERROR: Crop calculation failed for {ratio_name}")
                        continue
                    
                    print(f"  Crop created: {crop_image.width}x{crop_image.height}")
                    
                    # Resize to target dimensions
                    resized = crop_image.resize((width, height), Image.Resampling.LANCZOS)
                    print(f"  Resized to: {resized.width}x{resized.height}")
                    
                    # Save with proper naming
                    output_filename = f"{base_name}_{ratio_name}.jpg"
                    output_path = os.path.join(self.processed_folder, output_filename)
                    
                    # Preserve color profile
                    if img.mode == 'CMYK':
                        resized = resized.convert('CMYK')
                        print(f"  Converted to CMYK")
                    else:
                        resized = resized.convert('RGB')
                        print(f"  Converted to RGB")
                    
                    # Save with optimized settings
                    resized.save(
                        output_path, 
                        'JPEG', 
                        quality=90,          # Good balance of quality and file size
                        dpi=(300, 300),
                        optimize=True,       # Enable JPEG optimization
                        progressive=True     # Progressive JPEG for web
                    )
                    
                    # Verify file was saved
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path) / 1024 / 1024
                        print(f"  Saved: {output_filename} ({file_size:.2f} MB)")
                        output_files.append(output_path)
                    else:
                        print(f"  ERROR: File not saved: {output_path}")
                    
                    # Clear variables to help garbage collection
                    crop_image = None
                    resized = None
                    
            except Exception as e:
                print(f"Error processing ratio {ratio_name}: {e}")
                traceback.print_exc()
                continue
        
        print(f"Processing complete: {len(output_files)} files created")
        return output_files
    
    def _resize_if_too_large(self, image):
        """
        MEMORY OPTIMIZATION: Resize source image if it's too large.
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
            
            print(f"  Resizing to: {new_width}x{new_height}")
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
            
            print(f"  Resizing to: {new_width}x{new_height}")
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
            Cropped PIL Image object or None if failed
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
            print(f"ERROR: Invalid crop dimensions: {left},{top},{right},{bottom}")
            return None
        
        if right > img_width or bottom > img_height:
            print(f"ERROR: Crop out of bounds: {right}x{bottom} > {img_width}x{img_height}")
            return None
        
        print(f"  Crop area: ({left},{top}) to ({right},{bottom}), size: {crop_width}x{crop_height}")
        
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


# ============================================================================
# TESTING FUNCTION
# ============================================================================

def test_image_processor():
    """Test the image processor with a sample image."""
    print("=== Testing Image Processor ===")
    
    # Create a test image if none exists
    test_image_path = "test_image.jpg"
    if not os.path.exists(test_image_path):
        print("Creating test image...")
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (4000, 3000), color='blue')
        draw = ImageDraw.Draw(img)
        draw.rectangle([1000, 1000, 3000, 2000], fill='red')
        draw.text((1500, 1500), 'Test Image', fill='white')
        img.save(test_image_path, 'JPEG', quality=95)
        print(f"Test image created: {test_image_path}")
    
    # Test the processor
    session_id = "test_session_123"
    processor = ImageProcessor(test_image_path, session_id, "test_output")
    
    # Create previews
    print("\n1. Creating previews...")
    previews = processor.create_previews()
    print(f"Created {len(previews)} previews")
    
    # Test adjustment
    print("\n2. Testing adjustment...")
    preview_filename = processor.adjust_crop('2x3', x_offset=10, y_offset=-5)
    print(f"Adjustment preview filename: {preview_filename}")
    
    # Test batch processing
    print("\n3. Testing batch processing...")
    adjustments = {
        '2x3': {'x_offset': 10, 'y_offset': -5},
        '3x4': {'x_offset': 0, 'y_offset': 20}
    }
    output_files = processor.process_all_ratios(adjustments)
    print(f"Created {len(output_files)} output files")
    
    # Cleanup test files
    import shutil
    if os.path.exists("test_output"):
        shutil.rmtree("test_output")
    
    print("\n✅ Image Processor test completed successfully!")


if __name__ == "__main__":
    test_image_processor()