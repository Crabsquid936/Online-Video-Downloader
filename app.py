from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
from pathlib import Path

app = Flask(__name__)
CORS(app)  # Enable CORS for your GitHub Pages frontend

# Configuration
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB limit
ALLOWED_FORMATS = ['mp4', 'mkv', 'webm', 'avi']

# Create downloads directory
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Dictionary to track downloads
downloads_status = {}


def download_video(url, task_id):
    """Download video and save to disk"""
    try:
        downloads_status[task_id] = {'status': 'downloading', 'progress': 0}
        
        unique_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # Prefer MP4
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
        }
        
        filename = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get('ext', 'mp4')
            filename = os.path.join(DOWNLOAD_DIR, f"{unique_id}.{ext}")
        
        # Check file size
        file_size = os.path.getsize(filename)
        if file_size > MAX_FILE_SIZE:
            os.remove(filename)
            downloads_status[task_id] = {'status': 'error', 'message': 'File too large'}
            return None
        
        downloads_status[task_id] = {
            'status': 'complete',
            'filename': filename,
            'file_size': file_size
        }
        return filename
        
    except Exception as e:
        downloads_status[task_id] = {'status': 'error', 'message': str(e)}
        return None


def progress_hook(d):
    """Track download progress"""
    if d['status'] == 'downloading':
        total = d.get('total_bytes', 0)
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            progress = (downloaded / total) * 100
            # Optional: Update progress in downloads_status


@app.route('/download', methods=['POST'])
def download():
    """Main download endpoint"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Create a task ID
        task_id = str(uuid.uuid4())
        
        # Start download in a background thread
        thread = threading.Thread(target=download_video, args=(url, task_id))
        thread.daemon = True
        thread.start()
        
        return jsonify({'task_id': task_id, 'status': 'processing'}), 202
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download-sync', methods=['POST'])
def download_sync():
    """Synchronous download endpoint (for smaller files)"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        unique_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get('ext', 'mp4')
            filename = os.path.join(DOWNLOAD_DIR, f"{unique_id}.{ext}")
        
        # Check file size
        file_size = os.path.getsize(filename)
        if file_size > MAX_FILE_SIZE:
            os.remove(filename)
            return jsonify({'error': 'File too large (>500MB)'}), 413
        
        return send_file(filename, as_attachment=True, download_name=f"video.{ext}")
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    """Check download status"""
    if task_id not in downloads_status:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(downloads_status[task_id]), 200


@app.route('/file/<task_id>', methods=['GET'])
def get_file(task_id):
    """Download completed file"""
    if task_id not in downloads_status:
        return jsonify({'error': 'Task not found'}), 404
    
    status_info = downloads_status[task_id]
    
    if status_info['status'] != 'complete':
        return jsonify({'error': f"Download {status_info['status']}"}), 400
    
    filepath = status_info['filename']
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(filepath, as_attachment=True)


@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up old downloaded files"""
    try:
        deleted_count = 0
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                deleted_count += 1
        
        return jsonify({'message': f'Deleted {deleted_count} files'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
