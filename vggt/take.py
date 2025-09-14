import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client
import paramiko

# --- ⚙️ CONFIGURATION ---
# Your VM and project details.
# This should be the same for all team members.
VM_IP_ADDRESS = "204.12.168.146"
VM_USERNAME = "macbook"
# Path to the vggt repo on the VM
REMOTE_PROJECT_PATH = "/home/macbook/vggt" 
# ---

def download_from_supabase(supabase_client: Client, bucket_name: str, user_folder: str) -> tuple[Path, list]:
    """Downloads images from a specific user folder within a Supabase bucket."""
    
    # The local directory now includes the user's folder name for clarity
    local_dir = Path(f"./temp_downloads/{bucket_name}/{user_folder}")
    print(f"📦 Creating local directory: {local_dir}")
    local_dir.mkdir(parents=True, exist_ok=True)

    try:
        # --- THIS IS THE KEY CHANGE ---
        # We tell Supabase to list files *inside* the user's folder
        path_to_list = user_folder
        files = supabase_client.storage.from_(bucket_name).list(path_to_list)
        # ----------------------------

        if not files:
            print(f"⚠️ No files found in folder '{user_folder}'. Exiting.")
            sys.exit(1)

        print(f"Downloading image files from folder '{user_folder}'...")
        
        allowed_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        filenames = []
        for file_obj in files:
            file_name = file_obj['name']
            
            if not file_name.lower().endswith(allowed_extensions):
                print(f"   - Skipping non-image file: {file_name}")
                continue

            filenames.append(file_name)
            local_path = local_dir / file_name
            
            # We need to provide the full path to download the file
            full_file_path = f"{user_folder}/{file_name}"
            
            with open(local_path, "wb+") as f:
                res = supabase_client.storage.from_(bucket_name).download(full_file_path)
                f.write(res)
        
        print("✅ Image download complete.")
        return local_dir, filenames

    except Exception as e:
        print(f"❌ Error downloading from Supabase: {e}")
        sys.exit(1)


def upload_and_run_inference(local_dir: Path, filenames: list, bucket_name: str):
    """Connects to the VM, uploads files to an 'images' subdirectory, and runs inference."""
    
    # THIS IS THE KEY CHANGE: We define the parent 'scene_dir' and the 'images' subdirectory
    remote_scene_dir = f"{REMOTE_PROJECT_PATH}/data/{bucket_name}"
    remote_upload_dir = f"{remote_scene_dir}/images"
    
    print(f"\n🚀 Connecting to VM ({VM_USERNAME}@{VM_IP_ADDRESS})...")
    
    try:
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(VM_IP_ADDRESS, username=VM_USERNAME)
            print("✅ SSH connection successful.")

            # Create the required directory structure on the VM: .../data/[bucket_name]/images
            print(f"Ensuring remote directory structure exists: {remote_upload_dir}")
            ssh.exec_command(f"mkdir -p {remote_upload_dir}")

            # 1. Upload files into the 'images' subdirectory
            print(f"Uploading {len(filenames)} files to {remote_upload_dir} on VM...")
            sftp = ssh.open_sftp()
            for fname in filenames:
                local_path = str(local_dir / fname)
                remote_path = f"{remote_upload_dir}/{fname}"
                sftp.put(local_path, remote_path)
            sftp.close()
            print("✅ Upload complete.")

            # 2. THIS IS THE OTHER KEY CHANGE: The command now uses --scene_dir
            remote_script_path = f"{REMOTE_PROJECT_PATH}/demo_colmap.py"
            command = f"python3 {remote_script_path} --scene_dir {remote_scene_dir}"
            
            print(f"\n🧠 Running inference on VM...\nCommand: {command}\n")
            
            stdin, stdout, stderr = ssh.exec_command(command)
            
            print("--- VM INFERENCE OUTPUT ---")
            for line in iter(stdout.readline, ""):
                print(line, end="")
            print("---------------------------")

            error_output = stderr.read().decode()
            if error_output:
                print(f"❌ VM Error: {error_output}")
            else:
                print("\n🎉 Inference script finished successfully!")

    except Exception as e:
        print(f"❌ An error occurred during the remote process: {e}")
        sys.exit(1)

def download_results_locally(bucket_name: str):
    """Connects to the VM and downloads the 'sparse' results directory."""
    
    remote_results_dir = f"{REMOTE_PROJECT_PATH}/data/{bucket_name}/sparse"
    local_results_dir = Path(f"./results/{bucket_name}")
    local_results_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n⏬ Downloading results from {remote_results_dir}...")
    
    try:
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(VM_IP_ADDRESS, username=VM_USERNAME)

            sftp = ssh.open_sftp()
            
            # List all files in the remote sparse directory
            remote_files = sftp.listdir(remote_results_dir)
            
            for file_name in remote_files:
                remote_path = f"{remote_results_dir}/{file_name}"
                local_path = local_results_dir / file_name
                print(f"   - Copying {file_name} to {local_path}")
                sftp.get(remote_path, str(local_path))
                
            sftp.close()
            print(f"✅ Results successfully downloaded to {local_results_dir}")

    except Exception as e:
        print(f"❌ Could not download results: {e}")


if __name__ == "__main__":
    # Add a new argument for the user folder
    parser = argparse.ArgumentParser(description="Run VGGT pipeline on a specific user's folder in Supabase.")
    parser.add_argument("bucket_name", type=str, help="The Supabase bucket name.")
    parser.add_argument("user_folder", type=str, help="The user folder to process (e.g., 'ryan_duong@brown.edu').")
    args = parser.parse_args()

    # ... (Supabase connection logic remains the same) ...
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE")
    # ... (rest of the connection logic) ...
    supabase_client: Client = create_client(supabase_url, supabase_key)

    # --- FULL PIPELINE ---
    # Pass the new user_folder argument to the download function
    local_directory, file_list = download_from_supabase(supabase_client, args.bucket_name, args.user_folder)
    
    # We can use the user_folder name to create a unique scene on the VM
    # This replaces the bucket_name to avoid conflicts if you run both ryan's and timothy's photos
    upload_and_run_inference(local_directory, file_list, args.user_folder)
    
    download_results_locally(args.user_folder)