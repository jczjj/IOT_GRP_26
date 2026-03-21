from flask import Flask, render_template_string, send_from_directory, jsonify
import os
app = Flask(__name__)
ARC_DIR = "/home/sdn_service/poc/file_transfer/archive"
HTML = "..." # ( AJAX gallery template from previous response )
@app.route('/')
def index(): return render_template_string(HTML)
@app.route('/api/files')
def list_files(): return jsonify(sorted(os.listdir(ARC_DIR), reverse=True))
@app.route('/files/<filename>')
def get_file(filename): return send_from_directory(ARC_DIR, filename)
if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)