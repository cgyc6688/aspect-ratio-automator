"""
Aspect-Ratio Automator - Production Deployment Version
Simplified to fix deployment errors
"""

import os
import uuid
import zipfile
import tempfile
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_file, session

# Import utility modules
from utils.image_processor import ImageProcessor
from utils.dpi_checker import check_dpi

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# 1. FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# ============================================================================
# 2. APPLICATION CONFIGURATION
# ============================================================================

# File upload configuration (reduced for free tier)
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB

# File type restrictions
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'tiff', 'tif'}

# Use /tmp directory for Render compatibility
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'ara_uploads')
PROCESSED_FOLDER = os.path.join(tempfile.gettempdir(), 'ara_processed')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

# ============================================================================
# 3. LOGGING SETUP (SIMPLE)
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
app.logger = logging.getLogger(__name__)
app.logger.info('Aspect-Ratio Automator starting up...')

# ============================================================================
# 4. HELPER FUNCTIONS
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
    return name

# ============================================================================
# 5. ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main application page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads"""
    app.logger.info('Upload request received')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use JPG, PNG, or TIFF.'}), 400
    
    try:
        # Check file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > app.config['MAX_CONTENT_LENGTH']:
            max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
            return jsonify({'error': f'File exceeds maximum size of {max_mb}MB'}), 400
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Save file
        original_filename = secure_filename(file.filename)
        original_path = os.path.join(UPLOAD_FOLDER, f"{session_id}_{original_filename}")
        file.save(original_path)
        app.logger.info(f'File saved: {original_filename}')
        
        # Check DPI
        dpi_warning = check_dpi(original_path)
        
        # Process previews
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        previews = processor.create_previews()
        
        response_data = {
            'success': True,
            'session_id': session_id,
            'original_filename': original_filename,
            'dpi_warning': dpi_warning,
            'previews': previews
        }
        
        # Add warning for large files
        if file_size > 10 * 1024 * 1024:
            response_data['size_warning'] = 'Large file detected. Processing may be slower.'
        
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f'Upload error: {str(e)}')
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/adjust', methods=['POST'])
def adjust_crop():
    """Adjust crop position"""
    data = request.json
    session_id = data.get('session_id')
    ratio = data.get('ratio')
    x_offset = data.get('x_offset', 0)
    y_offset = data.get('y_offset', 0)
    
    if not session_id or not ratio:
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Find original file
    original_path = None
    for file in os.listdir(UPLOAD_FOLDER):
        if file.startswith(session_id):
            original_path = os.path.join(UPLOAD_FOLDER, file)
            break
    
    if not original_path:
        return jsonify({'error': 'File not found'}), 404
    
    try:
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        preview_path = processor.adjust_crop(ratio, x_offset, y_offset)
        
        if preview_path:
            preview_filename = os.path.basename(preview_path)
            return jsonify({
                'success': True,
                'preview_url': f'/preview/{preview_filename}'
            })
        else:
            return jsonify({'error': 'Adjustment failed'}), 500
            
    except Exception as e:
        app.logger.error(f'Adjustment error: {str(e)}')
        return jsonify({'error': f'Adjustment failed: {str(e)}'}), 500

@app.route('/preview/<filename>')
def get_preview(filename):
    """Serve preview images"""
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    preview_path = os.path.join(PROCESSED_FOLDER, filename)
    
    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype='image/jpeg')
    else:
        return jsonify({'error': 'Preview not found'}), 404

@app.route('/download', methods=['POST'])
def download_all():
    """Process all ratios and return ZIP"""
    data = request.json
    session_id = data.get('session_id')
    adjustments = data.get('adjustments', {})
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    # Find original file
    original_path = None
    original_filename = None
    
    for file in os.listdir(UPLOAD_FOLDER):
        if file.startswith(session_id):
            original_path = os.path.join(UPLOAD_FOLDER, file)
            parts = file.split('_', 1)
            if len(parts) > 1:
                original_filename = parts[1]
            else:
                original_filename = file
            break
    
    if not original_path:
        return jsonify({'error': 'File not found'}), 404
    
    try:
        # Process all images
        processor = ImageProcessor(original_path, session_id, PROCESSED_FOLDER)
        output_files = processor.process_all_ratios(adjustments)
        
        if not output_files:
            return jsonify({'error': 'Failed to process images'}), 500
        
        # Add PDF guide
        pdf_path = os.path.join('static', 'Printing_Guide.pdf')
        if os.path.exists(pdf_path):
            output_files.append(pdf_path)
        
        # Create ZIP
        base_name = os.path.splitext(original_filename)[0]
        clean_base_name = clean_filename(base_name)
        zip_filename = f"{clean_base_name}_printready.zip"
        zip_path = os.path.join(PROCESSED_FOLDER, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in output_files:
                if os.path.exists(file_path):
                    arcname = os.path.basename(file_path)
                    zipf.write(file_path, arcname)
        
        if not os.path.exists(zip_path):
            return jsonify({'error': 'Failed to create ZIP'}), 500
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        app.logger.error(f'Download error: {str(e)}')
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Simple health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Aspect-Ratio Automator'
    })

# ============================================================================
# 6. ERROR HANDLERS (VALID CODES ONLY)
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(413)
def too_large(error):
    max_mb = app.config['MAX_CONTENT_LENGTH'] / 1024 / 1024
    return jsonify({'error': f'File size exceeds {max_mb}MB limit'}), 413

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'500 error: {str(error)}')
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# 7. APPLICATION STARTUP
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    is_production = os.environ.get('FLASK_ENV') == 'production'
    
    if is_production:
        app.run(host='0.0.0.0', port=port)
    else:
        app.run(host='127.0.0.1', port=port, debug=True)