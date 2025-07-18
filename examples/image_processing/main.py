#!/usr/bin/env python3
"""
Image Processing Example with PyMonitor
This example demonstrates various image transformations with line-level monitoring.
"""

import monitoringpy
from monitoringpy.core.monitoring import init_monitoring
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import math

def create_sample_image(width=400, height=300):
    """Create a sample image with gradient and patterns if no image is provided."""
    # Create a gradient image
    img_array = np.zeros((height, width, 3), dtype=np.uint8)
    
    for y in range(height):
        for x in range(width):
            # Create a colorful gradient pattern
            r = int(255 * (x / width))
            g = int(255 * (y / height))
            b = int(255 * ((x + y) / (width + height)))
            img_array[y, x] = [r, g, b]
    
    # Add some geometric patterns
    center_x, center_y = width // 2, height // 2
    for y in range(height):
        for x in range(width):
            # Add circular patterns
            dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            if int(dist) % 20 < 10:
                img_array[y, x] = [255 - img_array[y, x, 0], 
                                 255 - img_array[y, x, 1], 
                                 255 - img_array[y, x, 2]]
    
    return Image.fromarray(img_array)

def apply_swirl_distortion(img_array, width, height):
    """Apply swirl distortion effect to an image array."""
    swirl_array = np.zeros_like(img_array)
    center_x, center_y = width // 2, height // 2
    
    for y in range(height):
        for x in range(width):
            # Calculate distance from center
            dx = x - center_x
            dy = y - center_y
            distance = math.sqrt(dx*dx + dy*dy)
            
            # Apply swirl transformation
            if distance > 0:
                angle = math.atan2(dy, dx) + distance * 0.01
                swirl_x = int(center_x + distance * math.cos(angle))
                swirl_y = int(center_y + distance * math.sin(angle))
                
                # Ensure coordinates are within bounds
                if 0 <= swirl_x < width and 0 <= swirl_y < height:
                    swirl_array[y, x] = img_array[swirl_y, swirl_x]
                else:
                    swirl_array[y, x] = [0, 0, 0]  # Black for out-of-bounds
            else:
                swirl_array[y, x] = img_array[y, x]
    
    return swirl_array

def apply_kaleidoscope_effect(img_array, width, height):
    """Apply kaleidoscope effect to an image array."""
    kaleidoscope_array = np.array(img_array)
    
    quarter_width = width // 2
    quarter_height = height // 2
    
    # Copy top-left quadrant to all other quadrants
    top_left = kaleidoscope_array[:quarter_height, :quarter_width]
    
    # Mirror horizontally for top-right
    kaleidoscope_array[:quarter_height, quarter_width:] = np.fliplr(top_left)
    
    # Mirror vertically for bottom-left
    kaleidoscope_array[quarter_height:, :quarter_width] = np.flipud(top_left)
    
    # Mirror both ways for bottom-right
    kaleidoscope_array[quarter_height:, quarter_width:] = np.flipud(np.fliplr(top_left))
    
    return kaleidoscope_array

@monitoringpy.pymonitor(mode="line")
def apply_cool_transformations(image):
    """Apply a series of cool image transformations using numpy arrays."""
    
    # 1. Color channel swap (RGB -> BGR)
    r, g, b = image.split()
    swapped_image = Image.merge("RGB", (b, g, r))
    
    # 2. Create a vibrant effect by enhancing saturation
    enhancer = ImageEnhance.Color(swapped_image)
    vibrant = enhancer.enhance(2.0)
    
    # 3. Apply a swirl distortion effect using numpy
    width, height = vibrant.size
    img_array = np.array(vibrant)
    swirl_array = apply_swirl_distortion(img_array, width, height)
    swirl_image = Image.fromarray(swirl_array)
    
    # 4. Apply a kaleidoscope effect using numpy
    kaleidoscope_array = apply_kaleidoscope_effect(swirl_image, width, height)
    kaleidoscope = Image.fromarray(kaleidoscope_array)
    
    # 5. Apply edge detection overlay
    edges = kaleidoscope.filter(ImageFilter.FIND_EDGES)
    edges = ImageEnhance.Contrast(edges).enhance(1.5)
    
    # 6. Blend original with edge detection
    final_image = Image.blend(kaleidoscope, edges, 0.3)
    
    # 7. Apply final color adjustments
    brightness_enhancer = ImageEnhance.Brightness(final_image)
    contrast_enhancer = ImageEnhance.Contrast(brightness_enhancer.enhance(1.2))
    result = contrast_enhancer.enhance(1.3)
    
    return result

def apply_vintage_filter(image):
    """Apply a vintage sepia-like filter."""
    # Convert to sepia
    sepia_image = ImageOps.colorize(image.convert("L"), "#704214", "#C0A882")
    
    # Add some noise for vintage effect
    width, height = sepia_image.size
    noise_array = np.random.randint(-20, 20, (height, width, 3))
    sepia_array = np.array(sepia_image)
    
    # Apply noise
    vintage_array = np.clip(sepia_array + noise_array, 0, 255).astype(np.uint8)
    
    return Image.fromarray(vintage_array)

def main():
    """Main function to demonstrate image processing with monitoring."""
    
    # Initialize monitoring
    monitor = init_monitoring(db_path="main.db", in_memory=False)
  
    # Create or load an image
    print("Creating sample image...")
    original_image = create_sample_image(600, 400)
    
    # Save original
    original_image.save("original_image.png")
    print("Original image saved as 'original_image.png'")
    
    # Apply cool transformations (this function is monitored)
    print("Applying cool transformations...")
    transformed_image = apply_cool_transformations(original_image)
    
    # Save transformed image
    transformed_image.save("transformed_image.png")
    print("Transformed image saved as 'transformed_image.png'")
    
    # Apply vintage filter
    
    vintage_image = apply_vintage_filter(original_image)
    vintage_image.save("vintage_image.png")
    

if __name__ == "__main__":
    main()
