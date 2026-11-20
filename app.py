import os
import uuid
import shutil
import sqlite3
from flask import Flask, request, send_from_directory, render_template, jsonify, abort

app = Flask(__name__)
UPLOAD_FOLDER = r'D:\FileShare\uploads'
DB_FILE = r'D:\FileShare\files.db'
MAX_STORAGE_BYTES = 300 * 1024 * 1024 * 1024
ADMIN_PASSWORD = '1234'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                downloads INTEGER DEFAULT 0
            )
        ''')

def format_size(size):
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} ТБ"

def get_used_storage():
    with sqlite3.connect(DB_FILE) as conn:
        res = conn.execute('SELECT SUM(size) FROM files').fetchone()[0]
    return res or 0

@app.route('/')
def index():
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute('SELECT id, original_name, size, downloads FROM files ORDER BY rowid DESC').fetchall()
    files = [{'id': r[0], 'name': r[1], 'size': format_size(r[2]), 'downloads': r[3]} for r in rows]

    used = get_used_storage()
    percent = min(round((used / MAX_STORAGE_BYTES) * 100, 1), 100)
    storage_info = {
        'used': format_size(used),
        'total': '300.00 ГБ',
        'percent': percent
    }
    return render_template('index.html', files=files, storage=storage_info)

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Пустое имя файла'}), 400

    file.seek(0, os.SEEK_END)
    incoming_size = file.tell()
    file.seek(0)

    used = get_used_storage()
    _, _, disk_free = shutil.disk_usage('D:\\')

    if used + incoming_size > MAX_STORAGE_BYTES:
        return jsonify({'error': 'Превышен лимит хранилища в 300 ГБ!'}), 400
    if incoming_size > disk_free - (5 * 1024 * 1024 * 1024):
        return jsonify({'error': 'На физическом диске D: заканчивается место!'}), 400

    file_id = uuid.uuid4().hex[:8]
    stored_name = f"{file_id}.bin"
    save_path = os.path.join(UPLOAD_FOLDER, stored_name)
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            'INSERT INTO files (id, original_name, stored_name, size) VALUES (?, ?, ?, ?)',
            (file_id, file.filename, stored_name, file_size)
        )

    return jsonify({'id': file_id, 'url': f'/d/{file_id}'})

@app.route('/d/<file_id>')
def download(file_id):
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute('SELECT original_name, stored_name FROM files WHERE id = ?', (file_id,)).fetchone()
        if not row:
            abort(404)
        conn.execute('UPDATE files SET downloads = downloads + 1 WHERE id = ?', (file_id,))
    return send_from_directory(UPLOAD_FOLDER, row[1], as_attachment=True, download_name=row[0])

@app.route('/delete/<file_id>', methods=['POST'])
def delete_file(file_id):
    data = request.get_json() or {}
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Неверный пароль админа!'}), 403

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute('SELECT stored_name FROM files WHERE id = ?', (file_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Файл не найден'}), 404

        file_path = os.path.join(UPLOAD_FOLDER, row[0])
        if os.path.exists(file_path):
            os.remove(file_path)

        conn.execute('DELETE FROM files WHERE id = ?', (file_id,))

    return jsonify({'status': 'deleted'})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)