import os
import sys
import torch
import glob
import numpy as np
import trimesh
import argparse
import re
from pathlib import Path
from supabase import create_client, Client
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images
from vggt.utils.geometry import unproject_depth_map_to_point_map

# Supabase configuration
SUPABASE_URL = "https://wgzwsdgrlmfigfnhtdrl.supabase.co/"
SUPABASE_SERVICE_ROLE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndnendzZGdybG1maWdmbmh0ZHJsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc4NDQxMSwiZXhwIjoyMDczMzYwNDExfQ.PevLf4LpAJ3qeNMrct4rGWeE5xJsifvlCL7oWQp38LM"
SUPABASE_BUCKET = "mentra_scenes"

def parse_bucket_path(path: str) -> str:
    """Parse and validate the bucket path argument."""
    # Pattern to match paths like mentra_scenes/class/bag or just class/bag
    pattern = r'^(?:mentra_scenes/)?([^/]+/[^/]+)$'
    match = re.match(pattern, path)
    
    if not match:
        raise argparse.ArgumentTypeError(
            "Invalid path format. Expected format: [mentra_scenes/]category/item"
            "\nExamples: mentra_scenes/class/bag, class/bag"
        )
    
    # Return just the category/item part
    return match.group(1)

def download_images_from_supabase(supabase_client: Client, bucket_name: str, user_folder: str = None) -> tuple[Path, list]:
    """Downloads images from Supabase bucket to local directory."""
    
    # Create local directory for downloads
    local_dir = Path(f"./data/{bucket_name}")
    if user_folder:
        local_dir = local_dir / user_folder
    
    images_dir = local_dir / "images"
    print(f"📦 Creating local directory: {images_dir}")
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        # List files in bucket (or specific folder)
        path_to_list = user_folder if user_folder else ""
        files = supabase_client.storage.from_(bucket_name).list(path_to_list)
        
        if not files:
            print(f"⚠️ No files found in bucket. Exiting.")
            sys.exit(1)

        print(f"Downloading image files from Supabase...")
        
        allowed_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        image_paths = []
        
        # Check if these are folders and recursively search
        for file_obj in files:
            file_name = file_obj['name']
            
            # Check if this is a folder (no extension typically means folder)
            if '.' not in file_name or file_obj.get('id') is None:
                print(f"📁 Found folder: {file_name}")
                # List files inside this folder
                folder_path = f"{path_to_list}/{file_name}" if path_to_list else file_name
                folder_files = supabase_client.storage.from_(bucket_name).list(folder_path)
                
                print(f"   Found {len(folder_files)} items in {file_name}")
                
                for inner_file in folder_files:
                    inner_file_name = inner_file['name']
                    print(f"     - Item: {inner_file_name}")
                    
                    if not inner_file_name.lower().endswith(allowed_extensions):
                        print(f"       Skipping (not an image)")
                        continue
                    
                    # Save all images directly in images_dir, with folder prefix in filename
                    # This flattens the structure so all images are in one directory
                    flat_file_name = f"{file_name}_{inner_file_name}"
                    local_path = images_dir / flat_file_name
                    image_paths.append(str(local_path))
                    
                    # Build the full file path for download
                    full_file_path = f"{folder_path}/{inner_file_name}"
                    
                    print(f"   - Downloading: {file_name}/{inner_file_name}")
                    with open(local_path, "wb+") as f:
                        res = supabase_client.storage.from_(bucket_name).download(full_file_path)
                        f.write(res)
            
            elif file_name.lower().endswith(allowed_extensions):
                # This is an image file at root level
                local_path = images_dir / file_name
                image_paths.append(str(local_path))
                
                # Build the full file path for download
                full_file_path = f"{user_folder}/{file_name}" if user_folder else file_name
                
                print(f"   - Downloading: {file_name}")
                with open(local_path, "wb+") as f:
                    res = supabase_client.storage.from_(bucket_name).download(full_file_path)
                    f.write(res)
        
        print(f"✅ Downloaded {len(image_paths)} images")
        return images_dir, image_paths

    except Exception as e:
        print(f"❌ Error downloading from Supabase: {e}")
        sys.exit(1)


def run_vggt_and_create_ply(image_paths: list, output_dir: Path):
    """Run VGGT inference and create PLY file directly."""
    
    print("\n🧠 Running VGGT inference...")
    
    # Setup device and dtype
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    
    print(f"   Device: {device}")
    print(f"   Dtype: {dtype}")
    
    # Initialize the model
    print("   Loading VGGT model...")
    model = VGGT.from_pretrained("facebook/VGGT-1B").to(device)
    print("✅ Model loaded")
    
    # Load and preprocess images
    print(f"\n📸 Processing {len(image_paths)} images...")
    images = load_and_preprocess_images(image_paths).to(device)
    
    # Run inference
    print("🚀 Running inference...")
    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            predictions = model(images)
    
    print("✅ Inference complete!")
    
    # Debug: print available keys
    print("\nAvailable prediction keys:", predictions.keys())
    
    # Extract point cloud from predictions
    print("\n🔧 Creating point cloud from predictions...")
    
    # Get world points directly - VGGT provides 3D points!
    world_points = predictions['world_points']  # Shape: [1, B, H, W, 3]
    depth = predictions['depth']  # Shape: [1, B, H, W, 1]
    
    print(f"World points shape: {world_points.shape}")
    print(f"Depth shape: {depth.shape}")
    
    # Remove the batch dimension and last dimension from depth
    world_points = world_points.squeeze(0)  # Shape: [B, H, W, 3]
    depth = depth.squeeze(0).squeeze(-1)  # Shape: [B, H, W]
    
    print(f"After squeezing - World points: {world_points.shape}, Depth: {depth.shape}")
    
    all_points = []
    all_colors = []
    
    from PIL import Image
    
    for i in range(len(image_paths)):
        # Get 3D points for this image
        points = world_points[i].cpu().numpy()  # Shape: [H, W, 3]
        depth_map = depth[i].cpu().numpy()  # Shape: [H, W]
        
        h, w = depth_map.shape
        
        # Reshape points to list
        points = points.reshape(-1, 3)
        
        # Filter out invalid points (depth == 0 or very far)
        depth_flat = depth_map.reshape(-1)
        valid_mask = (depth_flat > 0.01) & (depth_flat < 10)  # Filter extreme depths
        points = points[valid_mask]
        
        # Get colors from original image
        img = Image.open(image_paths[i])
        img = img.resize((w, h))
        colors = np.array(img).reshape(-1, 3)
        colors = colors[valid_mask]
        
        all_points.append(points)
        all_colors.append(colors)
    
    # Combine all points
    if all_points:
        combined_points = np.concatenate(all_points, axis=0)
        combined_colors = np.concatenate(all_colors, axis=0)
        
        print(f"\nPoint cloud statistics:")
        print(f"   Total points: {len(combined_points):,}")
        print(f"   Point shape: {combined_points.shape}")
        print(f"   Color shape: {combined_colors.shape}")
        print(f"   Point range X: [{combined_points[:, 0].min():.2f}, {combined_points[:, 0].max():.2f}]")
        print(f"   Point range Y: [{combined_points[:, 1].min():.2f}, {combined_points[:, 1].max():.2f}]")
        print(f"   Point range Z: [{combined_points[:, 2].min():.2f}, {combined_points[:, 2].max():.2f}]")
        
        # Create and save PLY
        output_dir.mkdir(parents=True, exist_ok=True)
        ply_path = output_dir / "point_cloud.ply"
        
        # Ensure colors are in uint8 format (0-255)
        if combined_colors.max() <= 1.0:
            combined_colors = (combined_colors * 255).astype(np.uint8)
        else:
            combined_colors = combined_colors.astype(np.uint8)
        
        point_cloud = trimesh.PointCloud(combined_points, colors=combined_colors)
        point_cloud.export(ply_path)
        
        print(f"\n✨ PLY file created: {ply_path}")
        print(f"   File size: {ply_path.stat().st_size / 1024:.2f} KB")
        
        # Verify PLY file
        print("\nVerifying PLY file...")
        loaded = trimesh.load(ply_path)
        print(f"   Loaded points: {len(loaded.vertices):,}")
        print(f"   Has colors: {loaded.colors is not None}")
        
        return ply_path
    else:
        print("\n❌ No valid points extracted!")
        return None


def main():
    parser = argparse.ArgumentParser(description="Run VGGT inference on images from Supabase and/or local directory")
    parser.add_argument(
        "--bucket-path", 
        type=parse_bucket_path,
        help="Path in the bucket (e.g., 'mentra_scenes/class/bag' or 'class/bag')",
        default=None
    )
    parser.add_argument(
        "--image-dir",
        type=str,
        help="Path to local directory containing images",
        default=None
    )
    args = parser.parse_args()

    if not args.bucket_path and not args.image_dir:
        parser.error("At least one of --bucket-path or --image-dir must be provided")

    print("=== VGGT to PLY Pipeline ===\n")
    
    all_image_paths = []
    output_base_dir = Path("./data")

    # Process Supabase images if bucket path is provided
    if args.bucket_path:
        print("🔗 Connecting to Supabase...")
        supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)
        print("✅ Connected to Supabase")
        
        images_dir, bucket_image_paths = download_images_from_supabase(
            supabase_client=supabase_client,
            bucket_name=SUPABASE_BUCKET,
            user_folder=args.bucket_path
        )
        if bucket_image_paths:
            all_image_paths.extend(bucket_image_paths)
            output_dir = images_dir.parent
        
    # Process local images if image directory is provided
    if args.image_dir:
        image_dir = Path(args.image_dir)
        if not image_dir.exists():
            print(f"❌ Image directory not found: {image_dir}")
            sys.exit(1)
            
        print(f"\n📂 Processing local images from: {image_dir}")
        image_extensions = ["*.png", "*.jpg", "*.jpeg"]
        local_image_paths = []
        for ext in image_extensions:
            local_image_paths.extend(glob.glob(str(image_dir / ext)))
            
        if local_image_paths:
            all_image_paths.extend(local_image_paths)
            # Create output directory based on input directory name
            output_dir = output_base_dir / image_dir.name
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            print(f"⚠️ No images found in {image_dir}")

    # Run VGGT and create PLY if we have any images
    if all_image_paths:
        print(f"\n🔍 Total images to process: {len(all_image_paths)}")
        ply_file = run_vggt_and_create_ply(all_image_paths, output_dir)
        print("\n🎉 Pipeline complete!")
        print(f"📍 PLY file location: {ply_file}")
    else:
        print("❌ No images to process from any source")
        sys.exit(1)


    # image_dir = Path("examples/room/images")
    # image_extensions = ["*.png", "*.jpg", "*.jpeg"]
    # image_paths = []
    # for ext in image_extensions:
    #     image_paths.extend(glob.glob(str(image_dir / ext)))
    
    # Run VGGT and create PLY directly (no COLMAP)
    output_dir = Path("./results")
    ply_file = run_vggt_and_create_ply(image_paths, output_dir)
    
    print("\n🎉 Pipeline complete!")
    print(f"📍 PLY file location: {ply_file}")


if __name__ == "__main__":
    main()