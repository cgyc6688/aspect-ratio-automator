"""
Aspect-Ratio Automator - Production Deployment Version
Optimized for Render.com with memory monitoring and file size limits
"""

# ============================================================================
# 1. IMPORTS & CONFIGURATION
# ============================================================================

import os
import uuid
import zipfile
import shutil
import logging
import tempfile
import psutil
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

# Import utility modules
from utils.image_processor import ImageProcessor
from utils.dpi_checker import check_dpi

# Load environment variables
from dotenv import load_dotenv
load_dotenv()  # Loads from .env file locally

# ============================================================================
# 2. FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)

# Security: Enable CORS for API requests
CORS(app)

# Rate limiting to prevent abuse
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "20 per hour"],  # Reduced for memory conservation
    storage_uri="memory://",
    strategy="fixed-window"
)

# ============================================================================
# 3. APPLICATION CONFIGURATION - MEMORY OPTIMIZED
# ============================================================================

# SECURITY: Get secret key from environment variable
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# FILE SIZE LIMITATION #1: Reduce max file size for free tier memory limits
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB (was 50MB)
MAX_RECOMMENDED_SIZE = 10 * 1024 * 1024  # 10MB recommended for free tier

# File type restrictions
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'tiff', 'tif'}

# Render uses ephemeral storage - use /tmp directory with session subfolders
def get_temp_directory(session_id=None):
    """Get temporary directory path, organized by session."""
    base_temp = tempfile.gettempdir()
    if session_id:
        return os.path.join(base_temp, f'ara_{session_id[:8]}')
    return os.path.join(base_temp, 'ara_temp')

app.config['UPLOAD_FOLDER'] = get_temp_directory()
app.config['PROCESSED_FOLDER'] = get_temp_directory()
app.config['SESSION_FOLDER'] = get_temp_directory()

# Session configuration
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = app.config['SESSION_FOLDER']
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Shorter for memory

# ============================================================================
# 4. MEMORY MONITORING #2 - HELPER FUNCTIONS
# ============================================================================

def get_memory_usage():
    """
    Get current memory usage information.
    Returns dict with memory stats in MB.
    """
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        system_memory = psutil.virtual_memory()
        
        return {
            'process_rss_mb': round(memory_info.rss / 1024 / 1024, 2),
            'process_vms_mb': round(memory_info.vms / 1024 / 1024, 2),
            'system_used_mb': round(system_memory.used / 1024 / 1024, 2),
            'system_available_mb': round(system_memory.available / 1024 / 1024, 2),
            'system_percent': round(system_memory.percent, 2),
            'memory_warning': memory_info.rss > 400 * 1024 * 1024  # Warn over 400MB
        }
    except Exception as e:
        return {'error': f'Memory monitoring error: {str(e)}'}

def check_memory_safe():
    """
    Check if memory usage is safe for processing.
    Returns True if safe, False if near limit.
    """
    memory = get_memory_usage()
    if isinstance(memory, dict) and 'process_rss_mb' in memory:
        # Render free tier has 512MB, stay under 400MB for safety
        return memory['process_rss_mb'] < 400
    return True

def cleanup_old_sessions():
    """
    Clean up old session files to prevent disk/memory buildup.
    Deletes files older than 1 hour.
    """
    try:
        current_time = datetime.now()
        temp_base = tempfile.gettempdir()
        
        for item in os.listdir(temp_base):
            if item.startswith('ara_'):
                item_path = os.path.join(temp_base, item)
                try:
                    # Check if directory is old
                    if os.path.isdir(item_path):
                        mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                        if current_time - mod_time > timedelta(hours=1):
                            shutil.rmtree(item_path, ignore_errors=True)
                            app.logger.info(f"Cleaned up old session: {item}")
                except Exception as e:
                    app.logger.warning(f"Could not clean up {item}: {e}")
    except Exception as e:
        app.logger.error(f"Error in session cleanup: {e}")

# ============================================================================
# 5. DIRECTORY SETUP WITH MEMORY AWARENESS
# ============================================================================

def setup_directories():
    """
    Create necessary directories with memory monitoring.
    """
    directories = [
        app.config['UPLOAD_FOLDER'],
        app.config['PROCESSED_FOLDER'],
        app.config['SESSION_FOLDER']
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            app.logger.info(f"Directory ensured: {directory}")
        except Exception as e:
            app.logger.error(f"Failed to create directory {directory}: {e}")
            # Fallback to simpler directory structure
            if 'UPLOAD' in directory:
                app.config['UPLOAD_FOLDER'] = '/tmp/ara_uploads'
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize directories
with app.app_context():
    setup_directories()
    cleanup_old_sessions()  # Clean up on startup

# ============================================================================
# 6. LOGGING SETUP WITH MEMORY LOGGING
# ============================================================================

# Configure logging for production
if not app.debug:
    # Basic logging to stdout (Render captures this)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s [MEM: %(process_rss_mb)MB]'
    )
else:
    logging.basicConfig(level=logging.DEBUG)

# Custom formatter that includes memory info
class MemoryLogFormatter(logging.Formatter):
    def format(self, record):
        # Add memory info to log record
        memory = get_memory_usage()
        if isinstance(memory, dict) and 'process_rss_mb' in memory:
            record.process_rss_mb = memory['process_rss_mb']
        else:
            record.process_rss_mb = 0
        
        return super().format(record)

# Apply custom formatter
for handler in logging.getLogger().handlers:
    handler.setFormatter(MemoryLogFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s [MEM: %(process_rss_mb)MB]'
    ))

app.logger = logging.getLogger(__name__)
app.logger.info('Aspect-Ratio Automator starting up with memory monitoring...')

# ============================================================================
# 7. HELPER FUNCTIONS
# ============================================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def clean_filename(filename):
    """Clean filename for safe usage."""
    import re
    name = re.sub(r'[^\w\s\-_.]', '', filename)
    name = name.replace(' ', '_')
    if len(name) > 100:
        name = name[:50] + "_" + name[-50:]
    return name

def get_session_file_path(session_id, original_filename):
    """Generate a unique file path for an uploaded file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_name = clean_filename(original_filename)
    filename = f"{session_id}_{timestamp}_{clean_name}"
    
    # Create session-specific directory
    session_upload_dir = get_temp_directory(session_id)
    os.makedirs(session_upload_dir, exist_ok=True)
    
    return os.path.join(session_upload_dir, filename)

def validate_file_size(file_size):
    """
    FILE SIZE LIMITATION #1: Validate file size with memory awareness.
    
    Args:
        file_size: Size in bytes
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Absolute limit from Flask config
    if file_size > app.config['MAX_CONTENT_LENGTH']:
        max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
        return False, f"File exceeds maximum size of {max_mb}MB"
    
    # Recommended limit for free tier memory
    if file_size > MAX_RECOMMENDED_SIZE:
        rec_mb = MAX_RECOMMENDED_SIZE / 1024 / 1024
        return True, f"Warning: File is large (> {rec_mb}MB). Free tier may have memory limitations."
    
    return True, "OK"

# ============================================================================
# 8. ROUTES WITH MEMORY MONITORING
# ============================================================================

@app.route('/')
def index():
    """Main application page"""
    memory = get_memory_usage()
    app.logger.info(f'Home page accessed. Memory: {memory.get("process_rss_mb", 0)}MB')
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@limiter.limit("5 per minute")  # Strict limit for memory conservation
def upload_file():
    """
    Handle file uploads with memory monitoring and size validation.
    """
    app.logger.info('Upload request received')
    
    # Check memory safety before processing
    if not check_memory_safe():
        app.logger.warning('Memory usage high, rejecting upload')
        return jsonify({
            'error': 'Server memory usage is high. Please try again in a moment.',
            'memory_status': get_memory_usage()
        }), 503
    
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    # Validate file
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use JPG, PNG, or TIFF.'}), 400
    
    # FILE SIZE LIMITATION: Check file size
    file.seek(0, 2)  # Seek to end to get size
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    is_valid, size_message = validate_file_size(file_size)
    
    if not is_valid:
        return jsonify({'error': size_message}), 400
    
    try:
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Create secure filename with session ID
        original_filename = secure_filename(file.filename)
        original_path = get_session_file_path(session_id, original_filename)
        
        # Log memory before save
        memory_before = get_memory_usage()
        app.logger.info(f'Memory before save: {memory_before.get("process_rss_mb", 0)}MB')
        
        # Save file
        file.save(original_path)
        app.logger.info(f'File saved: {original_filename} ({file_size/1024/1024:.2f}MB)')
        
        # Check DPI
        dpi_warning = check_dpi(original_path)
        if dpi_warning:
            app.logger.warning(f'Low DPI detected: {original_filename}')
        
        # Process image into all ratios with memory monitoring
        processor = ImageProcessor(original_path, session_id, get_temp_directory(session_id))
        
        # Check memory before processing
        if not check_memory_safe():
            app.logger.error('Memory unsafe for image processing')
            return jsonify({
                'error': 'Server memory limitations prevent processing this file. Try a smaller image.',
                'memory_status': get_memory_usage()
            }), 507  # 507 Insufficient Storage
        
        previews = processor.create_previews()
        
        # Log memory after processing
        memory_after = get_memory_usage()
        app.logger.info(f'Memory after processing: {memory_after.get("process_rss_mb", 0)}MB')
        app.logger.info(f'Memory delta: {memory_after.get("process_rss_mb", 0) - memory_before.get("process_rss_mb", 0):.2f}MB')
        
        response_data = {
            'success': True,
            'session_id': session_id,
            'original_filename': original_filename,
            'dpi_warning': dpi_warning,
            'previews': previews
        }
        
        # Add size warning if file was large
        if "Warning:" in size_message:
            response_data['size_warning'] = size_message
        
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f'Upload error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/adjust', methods=['POST'])
@limiter.limit("20 per minute")
def adjust_crop():
    """
    Adjust crop position with memory monitoring.
    """
    data = request.json
    session_id = data.get('session_id')
    ratio = data.get('ratio')
    x_offset = data.get('x_offset', 0)
    y_offset = data.get('y_offset', 0)
    
    app.logger.info(f'Adjust request: session={session_id}, ratio={ratio}')
    
    if not session_id or not ratio:
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Check memory
    if not check_memory_safe():
        return jsonify({'error': 'High memory usage. Try again later.'}), 503
    
    # Find original file in session directory
    session_dir = get_temp_directory(session_id)
    original_path = None
    
    if os.path.exists(session_dir):
        for file in os.listdir(session_dir):
            if file.endswith(('.jpg', '.jpeg', '.png', '.tiff', '.tif')):
                original_path = os.path.join(session_dir, file)
                break
    
    if not original_path or not os.path.exists(original_path):
        return jsonify({'error': 'File not found. Session may have expired.'}), 404
    
    try:
        processor = ImageProcessor(original_path, session_id, get_temp_directory(session_id))
        preview_path = processor.adjust_crop(ratio, x_offset, y_offset)
        
        if preview_path:
            preview_filename = os.path.basename(preview_path)
            app.logger.info(f'Adjustment saved: {preview_filename}')
            
            return jsonify({
                'success': True,
                'preview_url': f'/preview/{preview_filename}'
            })
        else:
            return jsonify({'error': 'Adjustment failed - memory issue'}), 500
            
    except Exception as e:
        app.logger.error(f'Adjustment error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Adjustment failed: {str(e)}'}), 500

@app.route('/preview/<filename>')
def get_preview(filename):
    """Serve preview images."""
    # Security check
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    # Look for file in all session directories
    temp_base = tempfile.gettempdir()
    preview_path = None
    
    for item in os.listdir(temp_base):
        if item.startswith('ara_'):
            potential_path = os.path.join(temp_base, item, filename)
            if os.path.exists(potential_path):
                preview_path = potential_path
                break
    
    if preview_path and os.path.exists(preview_path):
        return send_file(preview_path, mimetype='image/jpeg', max_age=300)
    else:
        return jsonify({'error': 'Preview not found'}), 404

@app.route('/download', methods=['POST'])
@limiter.limit("3 per minute")  # Very strict - downloads use lots of memory
def download_all():
    """
    Process all ratios and return a ZIP file with memory monitoring.
    """
    data = request.json
    session_id = data.get('session_id')
    adjustments = data.get('adjustments', {})
    
    app.logger.info(f'Download request for session: {session_id}')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    # CRITICAL: Check memory before starting batch processing
    memory_before = get_memory_usage()
    app.logger.info(f'Memory before download processing: {memory_before}')
    
    if not check_memory_safe():
        return jsonify({
            'error': 'Server memory too high for batch processing. Please try a smaller image or try again later.',
            'memory_status': memory_before
        }), 507
    
    # Find original file
    session_dir = get_temp_directory(session_id)
    original_path = None
    original_filename = None
    
    if os.path.exists(session_dir):
        for file in os.listdir(session_dir):
            if file.endswith(('.jpg', '.jpeg', '.png', '.tiff', '.tif')):
                original_path = os.path.join(session_dir, file)
                # Extract original filename
                parts = file.split('_')
                if len(parts) >= 3:
                    original_filename = '_'.join(parts[2:])
                else:
                    original_filename = file
                break
    
    if not original_path:
        return jsonify({'error': 'File not found. Please upload again.'}), 404
    
    try:
        # Process all images with adjustments
        processor = ImageProcessor(original_path, session_id, get_temp_directory(session_id))
        output_files = processor.process_all_ratios(adjustments)
        
        if not output_files:
            return jsonify({'error': 'Failed to process images'}), 500
        
        # Add Printing_Guide.pdf
        pdf_path = os.path.join('static', 'Printing_Guide.pdf')
        if os.path.exists(pdf_path):
            output_files.append(pdf_path)
        
        # Create ZIP file
        base_name = os.path.splitext(original_filename)[0]
        clean_base_name = clean_filename(base_name)
        zip_filename = f"{clean_base_name}_printready.zip"
        
        if not zip_filename or zip_filename == '_printready.zip':
            zip_filename = f"aspect_ratios_{session_id[:8]}.zip"
        
        zip_path = os.path.join(get_temp_directory(session_id), zip_filename)
        
        # Create ZIP with compression
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in output_files:
                    if os.path.exists(file_path):
                        arcname = os.path.basename(file_path)
                        zipf.write(file_path, arcname)
            
            # Check if ZIP was created
            if not os.path.exists(zip_path):
                return jsonify({'error': 'Failed to create ZIP file'}), 500
                
            zip_size = os.path.getsize(zip_path)
            app.logger.info(f'ZIP created: {zip_filename} ({zip_size/1024/1024:.2f}MB)')
            
        except Exception as e:
            app.logger.error(f'ZIP creation error: {str(e)}')
            return jsonify({'error': f'ZIP creation failed: {str(e)}'}), 500
        
        # Log memory usage after processing
        memory_after = get_memory_usage()
        memory_delta = memory_after.get('process_rss_mb', 0) - memory_before.get('process_rss_mb', 0)
        app.logger.info(f'Memory delta for download: {memory_delta:.2f}MB')
        
        # Send file
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        app.logger.error(f'Download error: {str(e)}', exc_info=True)
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

# ============================================================================
# 9. MEMORY MONITORING ENDPOINTS #2
# ============================================================================

@app.route('/health')
def health_check():
    """
    Health check endpoint with detailed memory monitoring.
    """
    memory = get_memory_usage()
    status = 'healthy' if check_memory_safe() else 'warning'
    
    return jsonify({
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'memory': memory,
        'file_size_limit_mb': app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024,
        'recommended_size_mb': MAX_RECOMMENDED_SIZE / 1024 / 1024,
        'session_count': len([d for d in os.listdir(tempfile.gettempdir()) 
                            if d.startswith('ara_') and os.path.isdir(os.path.join(tempfile.gettempdir(), d))])
    })

@app.route('/memory')
def memory_status():
    """
    Detailed memory status endpoint for debugging.
    """
    memory = get_memory_usage()
    
    # Get disk usage in temp directory
    temp_usage = 0
    temp_count = 0
    temp_base = tempfile.gettempdir()
    
    for item in os.listdir(temp_base):
        if item.startswith('ara_'):
            item_path = os.path.join(temp_base, item)
            try:
                if os.path.isdir(item_path):
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            temp_usage += os.path.getsize(file_path) if os.path.exists(file_path) else 0
                            temp_count += 1
            except:
                pass
    
    return jsonify({
        'memory': memory,
        'disk_usage': {
            'temp_files_count': temp_count,
            'temp_files_size_mb': round(temp_usage / 1024 / 1024, 2),
            'temp_directory': temp_base
        },
        'limits': {
            'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024,
            'recommended_file_size_mb': MAX_RECOMMENDED_SIZE / 1024 / 1024,
            'memory_warning_threshold_mb': 400,
            'memory_limit_mb': 512
        },
        'recommendations': [
            'Keep files under 10MB for best results',
            'Clear browser cache if experiencing issues',
            'Restart app if memory usage is consistently high'
        ]
    })

@app.route('/cleanup', methods=['POST'])
def cleanup_session():
    """
    Clean up files for a specific session to free memory.
    """
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    app.logger.info(f'Cleanup requested for session: {session_id}')
    
    files_removed = 0
    session_dir = get_temp_directory(session_id)
    
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
            files_removed = len(os.listdir(session_dir)) if os.path.exists(session_dir) else 1
        except Exception as e:
            app.logger.warning(f'Could not remove {session_dir}: {e}')
    
    # Also trigger global cleanup
    cleanup_old_sessions()
    
    return jsonify({
        'success': True, 
        'files_removed': files_removed,
        'memory_after_cleanup': get_memory_usage()
    })

# ============================================================================
# 10. ERROR HANDLERS WITH MEMORY INFO
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    app.logger.warning(f'404 error: {request.url}')
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(413)
def too_large(error):
    """Handle file too large errors with helpful message"""
    app.logger.warning(f'File too large: {request.remote_addr}')
    max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify({
        'error': f'File size exceeds {max_mb}MB limit',
        'max_size_mb': max_mb,
        'recommended_size_mb': MAX_RECOMMENDED_SIZE / 1024 / 1024
    }), 413

@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit errors"""
    app.logger.warning(f'Rate limit exceeded: {request.remote_addr}')
    return jsonify({'error': 'Rate limit exceeded. Please wait and try again.'}), 429

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors with memory info"""
    memory = get_memory_usage()
    app.logger.error(f'500 error: {str(error)}. Memory: {memory}', exc_info=True)
    return jsonify({
        'error': 'Internal server error',
        'memory_status': memory
    }), 500

@app.errorhandler(507)
def insufficient_storage(error):
    """Handle memory limit errors"""
    memory = get_memory_usage()
    app.logger.error(f'507 Insufficient storage: Memory: {memory}')
    return jsonify({
        'error': 'Server memory limits exceeded. Try a smaller file or try again later.',
        'memory_status': memory,
        'recommendation': 'Files under 10MB work best on free tier'
    }), 507

# ============================================================================
# 11. APPLICATION STARTUP WITH MEMORY CHECKS
# ============================================================================

if __name__ == '__main__':
    # Clean up on startup
    cleanup_old_sessions()
    
    # Log startup memory
    startup_memory = get_memory_usage()
    app.logger.info(f'Startup memory: {startup_memory}')
    
    # Check if we have psutil for memory monitoring
    try:
        import psutil
        app.logger.info('Memory monitoring enabled with psutil')
    except ImportError:
        app.logger.warning('psutil not installed. Memory monitoring limited.')
        app.logger.info('Install with: pip install psutil')
    
    # Get port from environment variable
    port = int(os.environ.get('PORT', 5000))
    
    # Determine environment
    is_production = os.environ.get('FLASK_ENV') == 'production'
    
    if is_production:
        # Production: Use all network interfaces
        app.logger.info(f'Starting production server on port {port}')
        app.run(host='0.0.0.0', port=port)
    else:
        # Development: Localhost with debug
        app.logger.info(f'Starting development server on port {port}')
        app.run(host='127.0.0.1', port=port, debug=True)